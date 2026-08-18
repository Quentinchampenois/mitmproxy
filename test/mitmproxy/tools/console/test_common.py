import urwid

from mitmproxy.test import tflow
from mitmproxy.tools.console import common
from mitmproxy.tools.console.common import extract_usage_tokens
from mitmproxy.tools.console.common import format_duration
from mitmproxy.tools.console.common import format_tokens
from mitmproxy.tools.console.common import format_ttft


def _canvas_text(widget: urwid.Widget, cols: int = 200) -> str:
    urwid.set_encoding("utf8")
    return "\n".join(row.decode("utf-8") for row in widget.render((cols,)).text)


def test_format_flow():
    for f in tflow.tflows():
        for render_mode in common.RenderMode:
            assert common.format_flow(f, render_mode=render_mode)
            assert common.format_flow(
                f, render_mode=render_mode, hostheader=True, focused=False
            )


def test_format_flow_inference():
    urwid.set_encoding("utf8")
    content = b'{"usage": {"input_tokens": 12, "output_tokens": 34}}'
    f = tflow.tflow(resp=tflow.tresp(content=content))

    list_text = _canvas_text(common.format_flow(f, render_mode=common.RenderMode.LIST))
    assert "\u219112 \u219334 1000ms" in list_text

    table_text = _canvas_text(
        common.format_flow(f, render_mode=common.RenderMode.TABLE)
    )
    assert "12/34 1000ms" in table_text

    plain_list_text = _canvas_text(
        common.format_flow(tflow.tflow(resp=True), render_mode=common.RenderMode.LIST)
    )
    assert "\u219112" not in plain_list_text
    assert "1000ms" not in plain_list_text
    assert "7b" in plain_list_text


def test_format_flow_inference_compressed():
    urwid.set_encoding("utf8")
    from mitmproxy.http import Headers
    from mitmproxy.net import encoding

    payload = b'{"usage": {"input_tokens": 12, "output_tokens": 34}}'
    for enc in ("gzip", "br"):
        f = tflow.tflow(
            resp=tflow.tresp(
                content=encoding.encode(payload, enc),
                headers=Headers(
                    (
                        (b"content-type", b"application/json"),
                        (b"content-encoding", enc.encode()),
                    )
                ),
            )
        )
        list_text = _canvas_text(
            common.format_flow(f, render_mode=common.RenderMode.LIST)
        )
        assert "\u219112 \u219334" in list_text, enc


def test_format_durations():
    assert format_duration(-0.1) == ("-100ms", "gradient_99")
    assert format_duration(0) == ("0ms", "gradient_99")
    assert format_duration(0.1) == ("100ms", "gradient_43")
    assert format_duration(100) == ("100s", "gradient_00")


def test_format_keyvals():
    assert common.format_keyvals(
        [
            ("aa", "bb"),
            ("cc", "dd"),
            ("ee", None),
        ]
    )
    wrapped = urwid.Pile(
        urwid.SimpleFocusListWalker(common.format_keyvals([("foo", "bar")]))
    )
    assert wrapped.render((30,))
    assert common.format_keyvals([("aa", wrapped)])


def test_extract_usage_tokens():
    assert extract_usage_tokens(
        b'{"usage": {"input_tokens": 10, "output_tokens": 20}}'
    ) == (10, 20)
    assert extract_usage_tokens(
        b'{"usage": {"prompt_tokens": 11, "completion_tokens": 22}}'
    ) == (11, 22)
    assert extract_usage_tokens(b"not json at all") == (None, None)
    assert extract_usage_tokens(b'{"usage":') == (None, None)
    assert extract_usage_tokens(b'{"foo": "bar"}') == (None, None)
    assert extract_usage_tokens(b"{}") == (None, None)
    assert extract_usage_tokens(b"[]") == (None, None)
    assert extract_usage_tokens(b"null") == (None, None)
    assert extract_usage_tokens(b"123") == (None, None)
    assert extract_usage_tokens(
        b'{"usage": {"input_tokens": "not an int", "output_tokens": 5}}'
    ) == (None, 5)
    assert extract_usage_tokens(
        b'{"usage": {"input_tokens": 5, "output_tokens": "nope"}}'
    ) == (5, None)
    assert extract_usage_tokens(b"") == (None, None)


def test_extract_usage_tokens_sse():
    sse = (
        b'data: {"delta": {"content": "he"}, "usage": null}\n\n'
        b'data: {"delta": {"content": "llo"}, "usage": null}\n\n'
        b'data: {"choices": [], "usage": {"input_tokens": 5, "output_tokens": 7}}\n\n'
        b"data: [DONE]\n\n"
    )
    assert extract_usage_tokens(sse) == (5, 7)


def test_extract_usage_tokens_sse_null_usage_only():
    sse = b'data: {"usage": null}\n\ndata: {"usage": null}\n\ndata: [DONE]\n\n'
    assert extract_usage_tokens(sse) == (None, None)


def test_format_tokens():
    assert format_tokens(None) == ""
    assert format_tokens(0) == "0"
    assert format_tokens(100) == "100"
    assert format_tokens(999) == "999"
    assert format_tokens(1200) == "1.2k"
    assert format_tokens(1000) == "1.0k"
    assert format_tokens(1100000) == "1.1M"


def test_token_threshold_styles():
    assert common.input_token_style(None) == "text"
    assert common.input_token_style(0) == "token_in_green"
    assert common.input_token_style(9999) == "token_in_green"
    assert common.input_token_style(10000) == "token_in_yellow"
    assert common.input_token_style(39999) == "token_in_yellow"
    assert common.input_token_style(40000) == "token_in_orange"
    assert common.input_token_style(119999) == "token_in_orange"
    assert common.input_token_style(120000) == "token_in_red"
    assert common.input_token_style(500000) == "token_in_red"

    assert common.output_token_style(None) == "text"
    assert common.output_token_style(599) == "token_out_green"
    assert common.output_token_style(600) == "token_out_yellow"
    assert common.output_token_style(1199) == "token_out_yellow"
    assert common.output_token_style(1200) == "token_out_orange"
    assert common.output_token_style(3999) == "token_out_orange"
    assert common.output_token_style(4000) == "token_out_red"


def test_format_usage_markup():
    markup = common.format_usage_markup(
        input_tokens=5000,
        output_tokens=500,
        ttft=None,
        style="",
    )
    assert ("token_in_green", "\u21915.0k") in markup
    assert ("token_out_green", "\u2193500") in markup


def test_format_usage_markup_ttft():
    markup = common.format_usage_markup(
        input_tokens=150000,
        output_tokens=5000,
        ttft=0.042,
        style="",
    )
    assert ("token_in_red", "\u2191150.0k") in markup
    assert ("token_out_red", "\u21935.0k") in markup
    assert ("text", " 42ms") in markup


def test_format_ttft():
    assert format_ttft(None) == ""
    assert format_ttft(0.042) == "42ms"
    assert format_ttft(1.2) == "1200ms"
    assert format_ttft(-0.1) == "0ms"


def test_truncated_text():
    urwid.set_encoding("utf8")
    half_width_text = common.TruncatedText("Half-width", [])
    full_width_text = common.TruncatedText("ＦＵＬＬ－ＷＩＤＴＨ", [])
    assert half_width_text.render((10,))
    assert full_width_text.render((10,))
