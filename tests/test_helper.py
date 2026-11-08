"""Tests for the ollama-launcher helper. Run: python3 -I -B -m unittest discover -s tests"""

import datetime as dt
import http.server
import importlib.machinery
import importlib.util
import io
import json
import os
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

HELPER = Path(__file__).resolve().parent.parent / "ollama-launcher"
loader = importlib.machinery.SourceFileLoader("ollama_launcher", str(HELPER))
spec = importlib.util.spec_from_loader("ollama_launcher", loader)
ol = importlib.util.module_from_spec(spec)
loader.exec_module(ol)

BIDI_OVERRIDE = chr(0x202E)  # built with chr() so no real bidi character sits in this file


def model(name, context, tools=True, blob="sha256-" + "a" * 64):
  return {"name": name, "context": context, "tools": tools, "blob": blob}


class TempCache(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.addCleanup(self.tmp.cleanup)
    patcher = mock.patch.object(ol, "CACHE_DIR", Path(self.tmp.name) / "cache")
    patcher.start()
    self.addCleanup(patcher.stop)


class Text(unittest.TestCase):
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

  def test_strips_bidi_and_control_characters(self):
    text = ol.clean_text("safe" + BIDI_OVERRIDE + "txt.exe\x00\x1b[31m\nnext", 100)
    self.assertNotIn(BIDI_OVERRIDE, text)
    self.assertNotIn("\x00", text)
    self.assertNotIn("\x1b", text)
    self.assertEqual(text, "safetxt.exe [31m next")

  def test_library_name(self):
    self.assertEqual(ol.library_name("qwen2.5:7b-32k", "qwen2.5:7b"), "qwen2.5")
    self.assertEqual(ol.library_name("qwen2.5:7b", ""), "qwen2.5")
    self.assertEqual(ol.library_name("someone/coder:latest", ""), "someone/coder")
    self.assertEqual(ol.library_name("../../etc:x", ""), "")

  def test_human_bytes_rejects_junk(self):
    self.assertEqual(ol.human_bytes(4683086978), "4.7 GB")
    for junk in (True, "x", -5, float("nan")):
      self.assertEqual(ol.human_bytes(junk), "")


class Time(unittest.TestCase):
  def test_future_stamp_counts_as_never(self):
    future = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=3)).isoformat()
    self.assertEqual(ol.age_sec(future), float("inf"))

  def test_past_and_missing(self):
    past = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=90)).isoformat()
    self.assertAlmostEqual(ol.age_sec(past), 90, delta=5)
    self.assertEqual(ol.age_sec(None), float("inf"))
    self.assertEqual(ol.age_sec("2026-01-01T00:00:00"), float("inf"))  # naive time


class Context(unittest.TestCase):
  def test_num_ctx(self):
    self.assertEqual(ol.num_ctx_from("num_ctx                        32768"), 32768)
    self.assertEqual(ol.num_ctx_from("temperature 0.2\nnum_ctx 8192\n"), 8192)
    self.assertIsNone(ol.num_ctx_from(None))

  def test_context_setting_inline_and_file(self):
    self.assertEqual(ol.context_setting("PATH=/x OLLAMA_CONTEXT_LENGTH=32768 OTHER=1"), 32768)
    self.assertEqual(ol.context_setting('# comment\nOLLAMA_CONTEXT_LENGTH="16384"\n'), 16384)
    self.assertIsNone(ol.context_setting("OLLAMA_HOST=0.0.0.0"))

  def test_environment_file_is_read(self):
    with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as handle:
      handle.write("OLLAMA_CONTEXT_LENGTH=65536\n")
    self.addCleanup(os.unlink, handle.name)
    shown = f"Environment=PATH=/usr/bin\nEnvironmentFiles={handle.name} (ignore_errors=no)\n"
    with mock.patch.object(ol.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, shown, "")):
      self.assertEqual(ol.server_default_context(), (65536, "server setting"))

  def test_default_when_unset(self):
    with mock.patch.object(ol.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "Environment=\nEnvironmentFiles=\n", "")):
      self.assertEqual(ol.server_default_context(), (4096, "Ollama default"))

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
    notes = ol.advice(model("qwen2.5:7b", 4096), [model("qwen2.5:7b-32k", 32768)])
    self.assertEqual(len(notes), 1)
    self.assertIn("Only 4k context", notes[0])
    self.assertIn("Use qwen2.5:7b-32k instead", notes[0])

  def test_small_context_without_copy(self):
    self.assertIn("larger num_ctx", ol.advice(model("tiny:1b", 2048), [])[0])

  def test_large_context_with_tools_is_ready(self):
    self.assertEqual(ol.advice(model("qwen2.5:7b-32k", 32768), []), [])

  def test_no_tools(self):
    notes = ol.advice(model("gemma:2b", 32768, tools=False), [])
    self.assertEqual(len(notes), 1)
    self.assertIn("No tool support", notes[0])


class Models(TempCache):
  def fake_ollama(self, tags, show=None, ps=None):
    def fetch(url, timeout, body=None, key=""):
      if url.endswith("/api/tags"):
        return tags
      if url.endswith("/api/ps"):
        return ps or {"models": []}
      return (show or {}).get(body["model"], {})
    return mock.patch.object(ol, "fetch_json", side_effect=fetch)

  def test_malformed_tags_give_empty_list_not_a_crash(self):
    with self.fake_ollama({"models": {"x": 1}}), mock.patch.object(ol, "server_default_context", return_value=(4096, "d")):
      result = ol.list_models()
    self.assertTrue(result["ok"])
    self.assertEqual(result["models"], [])

  def test_lists_local_models_with_flat_warning_and_no_network(self):
    blob = "FROM /x/blobs/sha256-" + "c" * 64
    tags = {"models": [
      {"name": "qwen2.5:7b", "size": 4683087332, "details": {"parameter_size": "7.6B", "quantization_level": "Q4_K_M"}},
      {"name": "qwen2.5:7b-32k", "size": 4683086978, "details": {}},
      {"name": "gpt-oss:120b-cloud", "remote_host": "https://ollama.com:443"},
      {"name": "bad name; rm", "size": 1},
    ]}
    show = {
      "qwen2.5:7b": {"capabilities": ["completion", "tools"], "modelfile": blob},
      "qwen2.5:7b-32k": {"capabilities": ["completion", "tools"], "modelfile": blob,
                         "parameters": "num_ctx 32768", "details": {"parent_model": "qwen2.5:7b"}},
    }
    with self.fake_ollama(tags, show), mock.patch.object(ol, "server_default_context", return_value=(4096, "Ollama default")), \
         mock.patch.object(ol, "fetch_text", side_effect=AssertionError("models must not use the network")):
      result = ol.list_models()
    names = [m["name"] for m in result["models"]]
    self.assertEqual(names, ["qwen2.5:7b-32k", "qwen2.5:7b"])  # ready first; cloud and bad names dropped
    plain = result["models"][1]
    self.assertIsInstance(plain["warning"], str)
    self.assertIn("Use qwen2.5:7b-32k instead", plain["warning"])
    self.assertEqual(result["models"][0]["warning"], "")
    self.assertEqual(result["families"], ["qwen2.5"])
    self.assertTrue(result["descriptionsDue"])
    self.assertNotIn("blob", plain)


class Descriptions(TempCache):
  def test_budget_stops_slow_fetches_and_keeps_what_arrived(self):
    def slow(url, timeout):
      time.sleep(0.6)
      return '<meta name="description" content="About ' + url.rsplit("/", 1)[-1] + '">'
    with mock.patch.object(ol, "DESCRIPTIONS_BUDGET_SEC", 1), mock.patch.object(ol, "fetch_text", side_effect=slow):
      started = time.monotonic()
      result = ol.descriptions(["alpha", "beta", "gamma"])
      elapsed = time.monotonic() - started
    self.assertLess(elapsed, 1.8)
    self.assertEqual(result["changed"], 1)
    entries = ol.description_entries()
    self.assertEqual(entries["alpha"]["text"], "About alpha")
    self.assertNotIn("gamma", entries)

  def test_outage_keeps_old_text_and_waits_a_day(self):
    old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=8)).isoformat()
    ol.write_cache("library.json", {"entries": {"qwen2.5": {"text": "Old text", "checkedAt": old}}})
    with mock.patch.object(ol, "fetch_text", side_effect=urllib.error.URLError("down")):
      ol.descriptions(["qwen2.5"])
    entry = ol.description_entries()["qwen2.5"]
    self.assertEqual(entry["text"], "Old text")
    self.assertFalse(ol.description_due(entry))

  def test_rejects_bad_family_names(self):
    with mock.patch.object(ol, "fetch_text", side_effect=AssertionError("must not fetch")):
      self.assertEqual(ol.descriptions(["../../x", "UPPER", "a b"])["changed"], 0)

  def test_failed_cache_write_leaves_no_temp_file(self):
    ol.write_cache("x.json", {"bad": object()})
    leftovers = list(ol.CACHE_DIR.iterdir()) if ol.CACHE_DIR.exists() else []
    self.assertEqual(leftovers, [])


class Credit(TempCache):
  BALANCE = {"included": {"balance_usd": 42.5, "allowance_usd": 60,
                          "period": {"from": "2026-10-30T19:31:46Z", "until": "2026-11-30T19:31:46Z"}},
             "purchased": {"balance_usd": 5}}

  def setUp(self):
    super().setUp()
    key = Path(self.tmp.name) / "api.key"
    key.write_text("TEST-KEY\n")
    patcher = mock.patch.object(ol, "KEY_FILE", key)
    patcher.start()
    self.addCleanup(patcher.stop)

  def http_error(self, code, retry=None):
    headers = {"Retry-After": str(retry)} if retry else {}
    return urllib.error.HTTPError(ol.BALANCE_URL, code, "x", headers, io.BytesIO(b""))

  def test_parse_balance(self):
    record = ol.parse_balance(self.BALANCE)
    self.assertEqual(record["totalLeftUsd"], 47.5)
    self.assertEqual(record["allowanceUsd"], 60)
    self.assertEqual(record["resetsAt"], "2026-11-30T19:31:46+00:00")

  def test_overdrawn_included_balance(self):
    self.assertEqual(ol.parse_balance({"included": {"balance_usd": -1.25, "allowance_usd": 60}})["totalLeftUsd"], -1.25)

  def test_rejects_empty_or_bogus(self):
    for payload in ({}, {"included": {"balance_usd": "lots"}}, {"included": {"balance_usd": True}}):
      with self.assertRaises(ValueError):
        ol.parse_balance(payload)

  def test_success_is_shared_for_a_minute(self):
    with mock.patch.object(ol, "fetch_json", return_value=self.BALANCE) as fetch:
      first, second = ol.credit(), ol.credit()
    self.assertEqual(fetch.call_count, 1)
    self.assertEqual(fetch.call_args.kwargs["key"], "TEST-KEY")
    self.assertTrue(second["ok"])
    self.assertFalse(second["stale"])

  def test_rate_limit_is_waited_out_and_marks_old_reading_stale(self):
    with mock.patch.object(ol, "fetch_json", return_value=self.BALANCE):
      ol.credit()
    cache = ol.read_cache("credit.json")
    cache["nextTryAt"] = ol.stamp()  # due now
    ol.write_cache("credit.json", cache)
    with mock.patch.object(ol, "fetch_json", side_effect=self.http_error(429, retry=600)) as fetch:
      first, second = ol.credit(), ol.credit()
    self.assertEqual(fetch.call_count, 1)
    self.assertTrue(second["ok"] and second["stale"])
    self.assertIn("429", second["error"])
    wait = (ol.parse_time(ol.read_cache("credit.json")["nextTryAt"]) - dt.datetime.now(dt.timezone.utc)).total_seconds()
    self.assertGreater(wait, 590)

  def test_rejected_key(self):
    with mock.patch.object(ol, "fetch_json", side_effect=self.http_error(401)):
      result = ol.credit()
    self.assertFalse(result["ok"])
    self.assertIn("rejected", result["error"])

  def test_missing_key(self):
    ol.KEY_FILE.write_text("")
    with mock.patch.object(ol, "fetch_json", side_effect=AssertionError("no key, no request")):
      self.assertIn("No Ollama API key", ol.credit()["error"])

  def test_redirect_is_not_followed_with_the_key(self):
    hits = []

    class Handler(http.server.BaseHTTPRequestHandler):
      def do_GET(self):
        hits.append((self.path, self.headers.get("Authorization")))
        if self.path == "/api/balance":
          self.send_response(302)
          self.send_header("Location", "/stolen")
          self.end_headers()
        else:
          self.send_response(200)
          self.end_headers()
          self.wfile.write(b"{}")

      def log_message(self, *args):
        pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    self.addCleanup(server.shutdown)
    url = f"http://127.0.0.1:{server.server_port}/api/balance"
    with self.assertRaises(urllib.error.HTTPError) as caught:
      ol.fetch_json(url, 5, key="SECRET")
    self.assertEqual(caught.exception.code, 302)
    caught.exception.close()
    self.assertEqual(hits, [("/api/balance", "Bearer SECRET")])


class Launch(TempCache):
  def test_model_names(self):
    for good in ("qwen2.5:7b", "qwen2.5:7b-32k", "someone/coder:latest", "llama3"):
      self.assertTrue(ol.MODEL_NAME.match(good), good)
    for bad in ("", "x;rm -rf ~", "a b", "$(id)", "-flag", "x:y:z", "a'b"):
      self.assertFalse(ol.MODEL_NAME.match(bad), bad)

  def test_script_runs_in_hostile_folder_with_local_model_everywhere(self):
    root = Path(self.tmp.name)
    marker = root / "PWNED"
    folder = root / "a b $(touch PWNED) `touch PWNED` it's\nz"
    folder.mkdir()
    stub_dir = root / "bin"
    stub_dir.mkdir()
    record = root / "record.json"
    stub = stub_dir / "opencode"
    stub.write_text(f'#!/bin/bash\nprintf \'%s\\0%s\\0%s\' "$PWD" "$OPENCODE_CONFIG_CONTENT" "$*" > {ol.shq(str(record))}\n')
    stub.chmod(0o755)
    script = ol.launch_script("qwen2.5:7b-32k", str(folder))
    subprocess.run(["bash", "-c", script], env={"PATH": f"{stub_dir}:/usr/bin:/bin", "HOME": str(root)},
                   cwd=root, stdin=subprocess.DEVNULL, capture_output=True, timeout=10)
    pwd, config, args = record.read_text().split("\0")
    self.assertEqual(pwd, str(folder))
    self.assertEqual(args, "--standalone")
    selection = {"providerID": "ollama", "model": "qwen2.5:7b-32k"}
    self.assertEqual(json.loads(config), {"model": selection, "agents": {"title": {"model": selection}}})
    self.assertFalse(marker.exists())

  def fake_tags(self):
    return mock.patch.object(ol, "fetch_json", return_value={"models": [{"name": "qwen2.5:7b-32k"}]})

  def test_relative_folder_resolves_under_home(self):
    home = Path(self.tmp.name) / "home"
    (home / "work").mkdir(parents=True)
    with self.fake_tags(), mock.patch.dict(os.environ, {"HOME": str(home)}), \
         mock.patch.object(ol.subprocess, "Popen") as popen:
      result = ol.launch("qwen2.5:7b-32k", "work")
    self.assertTrue(result["ok"])
    self.assertIn(f"cd -- '{home / 'work'}'", popen.call_args.args[0][-1])

  def test_rejections_never_spawn(self):
    with self.fake_tags(), mock.patch.object(ol.subprocess, "Popen") as popen:
      self.assertIn("Not a model name", ol.launch("x;id", "/tmp")["error"])
      self.assertIn("isn't installed", ol.launch("other:1b", "/tmp")["error"])
      self.assertIn("Folder not found", ol.launch("qwen2.5:7b-32k", "/nonexistent/dir")["error"])
    popen.assert_not_called()

  def test_missing_terminal_is_reported(self):
    with self.fake_tags(), mock.patch.object(ol.subprocess, "Popen", side_effect=FileNotFoundError(2, "No such file")):
      result = ol.launch("qwen2.5:7b-32k", "/tmp")
    self.assertFalse(result["ok"])
    self.assertIn("Couldn't open a terminal", result["error"])


class Main(unittest.TestCase):
  def test_unexpected_error_still_prints_json(self):
    out = io.StringIO()
    with mock.patch.object(ol, "run", side_effect=KeyError("boom")), redirect_stdout(out):
      code = ol.main(["x", "models"])
    self.assertEqual(code, 1)
    self.assertEqual(json.loads(out.getvalue()), {"ok": False, "error": "Helper error: KeyError"})


if __name__ == "__main__":
  unittest.main()
