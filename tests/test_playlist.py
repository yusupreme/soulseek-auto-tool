import httpx
import pytest

from soulseek_auto_tool import playlist


def test_full_url_is_kept_but_tracking_params_are_dropped():
    url = "https://soundcloud.com/user/sets/mix/s-AbC123?ref=clipboard&si=xyz"
    assert playlist.resolve_url(url) == "https://soundcloud.com/user/sets/mix/s-AbC123"


def test_short_link_is_expanded_and_keeps_secret_token(monkeypatch):
    def fake_get(url, **kwargs):
        assert kwargs["follow_redirects"] is False
        return httpx.Response(302, headers={"location": "https://soundcloud.com/u/sets/p/s-SECRET?ref=clipboard&c=1"})

    monkeypatch.setattr(playlist.httpx, "get", fake_get)
    assert playlist.resolve_url("https://on.soundcloud.com/abc") == "https://soundcloud.com/u/sets/p/s-SECRET"


def test_parse_track_page_reads_title_and_uploader():
    html = (
        "<title>Stream Spatial &amp; Sequence by Oscar Mulero | Listen online</title>"
        '<meta property="og:title" content="Spatial &amp; Sequence">'
    )
    assert playlist.parse_track_page(html) == ("Spatial & Sequence", "Oscar Mulero")


def test_parse_track_page_returns_none_for_unknown_html():
    assert playlist.parse_track_page("<html>nothing here</html>") is None


def test_dead_short_link_gives_a_clear_error(monkeypatch):
    monkeypatch.setattr(playlist.httpx, "get", lambda url, **kw: httpx.Response(404))
    with pytest.raises(RuntimeError, match="share link"):
        playlist.resolve_url("https://on.soundcloud.com/dead")
