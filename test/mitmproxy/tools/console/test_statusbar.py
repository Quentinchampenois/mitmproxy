import pytest
import urwid

from mitmproxy.test import tflow
from mitmproxy.tools.console import statusbar
from mitmproxy.tools.console.statusbar import compute_usage_totals


def _json_resp(content: bytes):
    from mitmproxy.http import Headers

    return tflow.tresp(
        content=content,
        headers=Headers(((b"content-type", b"application/json"),)),
    )


def test_compute_usage_totals_sums_multiple_flows():
    flows = [
        tflow.tflow(
            resp=_json_resp(b'{"usage": {"input_tokens": 10, "output_tokens": 20}}')
        ),
        tflow.tflow(
            resp=_json_resp(b'{"usage": {"input_tokens": 5, "output_tokens": 7}}')
        ),
    ]
    assert compute_usage_totals(flows) == (15, 27, 2)


def test_compute_usage_totals_skips_non_json():
    flows = [
        tflow.tflow(resp=tflow.tresp(content=b"plain text body")),
        tflow.tflow(
            resp=_json_resp(b'{"usage": {"input_tokens": 3, "output_tokens": 4}}')
        ),
    ]
    assert compute_usage_totals(flows) == (3, 4, 1)


def test_compute_usage_totals_skips_no_response():
    flows = [
        tflow.tflow(resp=False),
        tflow.tflow(
            resp=_json_resp(b'{"usage": {"input_tokens": 2, "output_tokens": 3}}')
        ),
    ]
    assert compute_usage_totals(flows) == (2, 3, 1)


def test_compute_usage_totals_accumulates_fallback_variants():
    flows = [
        tflow.tflow(
            resp=_json_resp(b'{"usage": {"prompt_tokens": 11, "completion_tokens": 22}}')
        ),
        tflow.tflow(
            resp=_json_resp(b'{"usage": {"input_tokens": 1, "output_tokens": 2}}')
        ),
    ]
    assert compute_usage_totals(flows) == (12, 24, 2)


def test_compute_usage_totals_no_inference_flows():
    assert compute_usage_totals([]) == (0, 0, 0)
    flows = [tflow.tflow(resp=tflow.tresp(content=b"not json"))]
    assert compute_usage_totals(flows) == (0, 0, 0)


def test_compute_usage_totals_skips_missing_body():
    flows = [
        tflow.tflow(
            resp=_json_resp(
                b'{"usage": {"input_tokens": 1, "output_tokens": 2}}'
            )
        ),
        tflow.tflow(resp=tflow.tresp(content=None)),
    ]
    assert compute_usage_totals(flows) == (1, 2, 1)


def test_compute_usage_totals_decompresses_encoded_bodies():
    from mitmproxy.http import Headers
    from mitmproxy.net import encoding

    payload = b'{"usage": {"input_tokens": 10, "output_tokens": 20}}'
    flows = [
        tflow.tflow(
            resp=tflow.tresp(
                content=encoding.encode(payload, "gzip"),
                headers=Headers(
                    (
                        (b"content-type", b"application/json"),
                        (b"content-encoding", b"gzip"),
                    )
                ),
            )
        ),
        tflow.tflow(
            resp=tflow.tresp(
                content=encoding.encode(payload, "br"),
                headers=Headers(
                    (
                        (b"content-type", b"application/json"),
                        (b"content-encoding", b"br"),
                    )
                ),
            )
        ),
    ]
    assert compute_usage_totals(flows) == (20, 40, 2)


def test_compute_usage_totals_event_stream():
    from mitmproxy.http import Headers

    sse = (
        b'data: {"delta": {"content": "he"}, "usage": null}\n\n'
        b'data: {"choices": [], "usage": {"input_tokens": 10, "output_tokens": 20}}\n\n'
        b"data: [DONE]\n\n"
    )
    flows = [
        tflow.tflow(
            resp=tflow.tresp(
                content=sse,
                headers=Headers(((b"content-type", b"text/event-stream"),)),
            )
        )
    ]
    assert compute_usage_totals(flows) == (10, 20, 1)


async def test_statusbar(console, monkeypatch):
    console.options.update(
        modify_headers=[":~q:foo:bar"],
        modify_body=[":~q:foo:bar"],
        ignore_hosts=["example.com", "example.org"],
        tcp_hosts=["example.tcp"],
        intercept="~q",
        view_filter="~dst example.com",
        stickycookie="~dst example.com",
        stickyauth="~dst example.com",
        console_default_contentview="javascript",
        anticache=True,
        anticomp=True,
        showhost=True,
        server_replay_refresh=False,
        server_replay_extra="kill",
        upstream_cert=False,
        stream_large_bodies="3m",
        mode=["transparent"],
    )
    console.options.update(view_order="url", console_focus_follow=True)
    monkeypatch.setattr(console.addons.get("clientplayback"), "count", lambda: 42)
    monkeypatch.setattr(console.addons.get("serverplayback"), "count", lambda: 42)
    monkeypatch.setattr(statusbar.StatusBar, "refresh", lambda x: None)

    bar = statusbar.StatusBar(console)  # this already causes a redraw
    assert bar.ib._w


@pytest.mark.parametrize(
    "message,ready_message",
    [
        ("", [("", ""), ("warn", "")]),
        (
            ("info", "Line fits into statusbar"),
            [("info", "Line fits into statusbar"), ("warn", "")],
        ),
        (
            "Line doesn't fit into statusbar",
            [("", "Line doesn'\u2026"), ("warn", "(more in eventlog)")],
        ),
        (
            ("alert", "Two lines.\nFirst fits"),
            [("alert", "Two lines."), ("warn", "(more in eventlog)")],
        ),
        (
            "Two long lines\nFirst doesn't fit",
            [("", "Two long li\u2026"), ("warn", "(more in eventlog)")],
        ),
    ],
)
def test_shorten_message(message, ready_message):
    assert statusbar.shorten_message(message, max_width=30) == ready_message


def test_shorten_message_narrow():
    shorten_msg = statusbar.shorten_message("error", max_width=4)
    assert shorten_msg == [("", "\u2026"), ("warn", "(more in eventlog)")]


async def test_console_quickhelp_option(console, monkeypatch):
    """Test that console_quickhelp option controls the display of quick help bar."""
    monkeypatch.setattr(statusbar.StatusBar, "refresh", lambda x: None)

    # quickhelp enabled (default)
    console.options.console_quickhelp_visible = True
    bar = statusbar.StatusBar(console)
    assert isinstance(bar.ab._w, urwid.Pile)
    assert len(bar.ab._w.contents) == 2
    assert isinstance(bar.ab.top._w, urwid.Columns)
    assert isinstance(bar.ab.bottom._w, urwid.Columns)

    # quickhelp disabled
    console.options.console_quickhelp_visible = False
    bar2 = statusbar.StatusBar(console)
    assert isinstance(bar2.ab._w, urwid.Pile)
    assert len(bar2.ab._w.contents) == 0


async def test_console_quickhelp_toggle(console, monkeypatch):
    """Test that toggling console_quickhelp option updates the display."""
    monkeypatch.setattr(statusbar.StatusBar, "refresh", lambda x: None)

    bar = statusbar.StatusBar(console)

    # quickhelp enabled (default)
    assert console.options.console_quickhelp_visible is True
    bar.ab.show_quickhelp()
    assert isinstance(bar.ab._w, urwid.Pile)
    assert len(bar.ab._w.contents) == 2
    assert isinstance(bar.ab.top._w, urwid.Columns)
    assert isinstance(bar.ab.bottom._w, urwid.Columns)

    # quickhelp disabled
    console.options.console_quickhelp_visible = False
    bar.ab.show_quickhelp()
    assert isinstance(bar.ab._w, urwid.Pile)
    assert len(bar.ab._w.contents) == 0

    # quickhelp toggling
    console.options.console_quickhelp_visible = True
    bar.ab.show_quickhelp()
    assert isinstance(bar.ab._w, urwid.Pile)
    assert len(bar.ab._w.contents) == 2
    assert isinstance(bar.ab.top._w, urwid.Columns)
    assert isinstance(bar.ab.bottom._w, urwid.Columns)


async def test_console_quickhelp_hotkey(console):
    """Test that the 'H' hotkey toggles the console_quickhelp option."""
    assert console.options.console_quickhelp_visible is True

    console.type("H")
    assert console.options.console_quickhelp_visible is False

    console.type("H")
    assert console.options.console_quickhelp_visible is True


async def test_console_quickhelp_prompts_visible_when_disabled(console, monkeypatch):
    """Test that prompts and messages are visible even when quickhelp is disabled."""
    monkeypatch.setattr(statusbar.StatusBar, "refresh", lambda x: None)

    # Disable quickhelp
    console.options.console_quickhelp_visible = False
    bar = statusbar.StatusBar(console)

    # Initially, Pile should be empty (quickhelp disabled)
    assert isinstance(bar.ab._w, urwid.Pile)
    assert len(bar.ab._w.contents) == 0

    # Show a message - Pile should now contain widgets
    bar.ab.sig_message("Test message", expire=None)
    assert len(bar.ab._w.contents) == 2
    assert isinstance(bar.ab.top._w, urwid.Text)

    # After showing quickhelp again (when message expires), should hide if disabled
    bar.ab.show_quickhelp()
    assert len(bar.ab._w.contents) == 0

    # Show a prompt - Pile should contain widgets
    bar.ab.sig_prompt("Test prompt", None, lambda x: None)
    assert len(bar.ab._w.contents) == 2
    assert isinstance(bar.ab.top._w, urwid.Edit)

    # Dismiss prompt
    bar.ab.prompt_done()
    assert len(bar.ab._w.contents) == 0
