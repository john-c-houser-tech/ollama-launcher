"""Tests for the ollama-launcher helper. Run: python3 -I -m unittest discover -s tests"""

import importlib.machinery
import importlib.util
import json
import subprocess
import unittest
from pathlib import Path

HELPER = Path(__file__).resolve().parent.parent / "ollama-launcher"
loader = importlib.machinery.SourceFileLoader("ollama_launcher", str(HELPER))
spec = importlib.util.spec_from_loader("ollama_launcher", loader)
ol = importlib.util.module_from_spec(spec)
loader.exec_module(ol)


def model(name, context, tools=True, blob="sha256-" + "a" * 64):
  return {"name": name, "context": context, "tools": tools, "blob": blob}


class Descriptions(unittest.TestCase):
  def test_reads_meta_description_and_unescapes(self):
    page = '<head><meta name="description" content="Qwen2.5 is Alibaba&#39;s model.  Multilingual. "></head>'
    self.assertEqual(ol.parse_description(page), "Qwen2.5 is Alibaba's model. Multilingual.")

  def test_missing_description(self):
    self.assertEqual(ol.parse_description("<html></html>"), "")

  def test_markup_shaped_text_stays_plain_and_capped(self):
    page = '<meta name="description" content="&lt;img src=https://example.invalid/t&gt;' + "x" * 600 + '">'
    text = ol.parse_description(page)
    self.assertTrue(text.startswith("<img src="))  # shown as plain text by the QML
    self.assertLessEqual(len(text), ol.MAX_DESCRIPTION)

  def test_library_name(self):
    self.assertEqual(ol.library_name("qwen2.5:7b-32k", "qwen2.5:7b"), "qwen2.5")
    self.assertEqual(ol.library_name("qwen2.5:7b", ""), "qwen2.5")
    self.assertEqual(ol.library_name("someone/coder:latest", ""), "someone/coder")
    self.assertEqual(ol.library_name("../../etc:x", ""), "")


class Context(unittest.TestCase):
  def test_num_ctx(self):
    self.assertEqual(ol.num_ctx_from("num_ctx                        32768"), 32768)
    self.assertEqual(ol.num_ctx_from("temperature 0.2\nnum_ctx 8192\n"), 8192)
    self.assertIsNone(ol.num_ctx_from(None))

  def test_weights_blob(self):
    mf = "# FROM qwen2.5:7b\nFROM /home/x/.ollama/models/blobs/sha256-" + "b" * 64 + "\nPARAMETER num_ctx 32768"
    self.assertEqual(ol.weights_blob(mf), "sha256-" + "b" * 64)
    self.assertEqual(ol.weights_blob("FROM qwen2.5:7b"), "")

  def test_short_tokens(self):
    self.assertEqual(ol.short_tokens(4096), "4k")
    self.assertEqual(ol.short_tokens(32768), "32k")
    self.assertEqual(ol.short_tokens(512), "512")


class Advice(unittest.TestCase):
  def test_small_context_points_to_larger_copy(self):
    small, big = model("qwen2.5:7b", 4096), model("qwen2.5:7b-32k", 32768)
    notes = ol.advice(small, [big])
    self.assertEqual(len(notes), 1)
    self.assertIn("Only 4k context", notes[0])
    self.assertIn("Use qwen2.5:7b-32k instead", notes[0])

  def test_small_context_without_copy(self):
    notes = ol.advice(model("tiny:1b", 2048), [])
    self.assertIn("larger num_ctx", notes[0])

  def test_large_context_with_tools_is_ready(self):
    self.assertEqual(ol.advice(model("qwen2.5:7b-32k", 32768), []), [])

  def test_no_tools(self):
    notes = ol.advice(model("gemma:2b", 32768, tools=False), [])
    self.assertEqual(len(notes), 1)
    self.assertIn("No tool support", notes[0])


class Credit(unittest.TestCase):
  def test_parse_balance(self):
    record = ol.parse_balance({"included": {"balance_usd": 42.5, "allowance_usd": 60,
                                            "period": {"from": "2026-10-30T19:31:46Z", "until": "2026-11-30T19:31:46Z"}},
                               "purchased": {"balance_usd": 5}})
    self.assertEqual(record["totalLeftUsd"], 47.5)
    self.assertEqual(record["allowanceUsd"], 60)
    self.assertEqual(record["resetsAt"], "2026-11-30T19:31:46+00:00")

  def test_overdrawn_included_balance(self):
    record = ol.parse_balance({"included": {"balance_usd": -1.25, "allowance_usd": 60}})
    self.assertEqual(record["totalLeftUsd"], -1.25)

  def test_rejects_empty_or_bogus(self):
    for payload in ({}, {"included": {"balance_usd": "lots"}}, {"included": {"balance_usd": True}}):
      with self.assertRaises(ValueError):
        ol.parse_balance(payload)

  def test_bad_period_is_dropped(self):
    record = ol.parse_balance({"included": {"balance_usd": 1, "allowance_usd": 60, "period": {"until": "soon"}}})
    self.assertEqual(record["resetsAt"], "")


class Launch(unittest.TestCase):
  def test_model_names(self):
    for good in ("qwen2.5:7b", "qwen2.5:7b-32k", "someone/coder:latest", "llama3"):
      self.assertTrue(ol.MODEL_NAME.match(good), good)
    for bad in ("", "x;rm -rf ~", "a b", "$(id)", "-flag", "x:y:z", "a'b"):
      self.assertFalse(ol.MODEL_NAME.match(bad), bad)

  def test_script_quotes_folder_and_sets_model(self):
    script = ol.launch_script("qwen2.5:7b-32k", "/home/me/it's here")
    result = subprocess.run(
      ["bash", "-c", script.replace("opencode --standalone", 'printf "%s|%s" "$PWD" "$OPENCODE_CONFIG_CONTENT"')
       .replace("cd -- ", "true -- ").replace("status=$?", "exit 0")],
      capture_output=True, text=True, timeout=5)
    pwd, config = result.stdout.split("|", 1)
    self.assertEqual(json.loads(config), {"model": {"providerID": "ollama", "model": "qwen2.5:7b-32k"}})

  def test_script_cd_uses_quoted_folder(self):
    script = ol.launch_script("m:1", "/tmp/$(touch /tmp/pwned)'x")
    self.assertIn("cd -- '/tmp/$(touch /tmp/pwned)'\\''x'", script)
    self.assertIn("opencode --standalone", script)

  def test_launch_rejects_bad_name_without_spawning(self):
    result = subprocess.run(["python3", "-I", str(HELPER), "launch", "x;id", "/tmp"], capture_output=True, text=True, timeout=10)
    self.assertEqual(result.returncode, 2)
    self.assertFalse(json.loads(result.stdout)["ok"])


if __name__ == "__main__":
  unittest.main()
