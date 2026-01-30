# -*- coding: utf-8 -*-
"""Unit tests for URL Reader (Jina Reader version)"""

from unittest.mock import MagicMock, patch

import pytest


class TestUrlExtraction:
    """Tests for URL extraction functions"""

    @pytest.mark.unit
    def test_extract_urls_finds_http_urls(self):
        """Should find HTTP URLs in text"""
        from agent.agno_agent.tools.url_reader import extract_urls

        text = "Check out http://example.com and https://test.org/path"
        urls = extract_urls(text)

        assert len(urls) == 2
        assert "http://example.com" in urls
        assert "https://test.org/path" in urls

    @pytest.mark.unit
    def test_extract_urls_removes_trailing_punctuation(self):
        """Should remove trailing punctuation from URLs"""
        from agent.agno_agent.tools.url_reader import extract_urls

        text = "Visit https://example.com. Also see https://test.org!"
        urls = extract_urls(text)

        assert "https://example.com" in urls
        assert "https://test.org" in urls
        # Should not have trailing punctuation
        assert "https://example.com." not in urls

    @pytest.mark.unit
    def test_extract_urls_deduplicates(self):
        """Should return unique URLs only"""
        from agent.agno_agent.tools.url_reader import extract_urls

        text = "https://example.com https://example.com https://test.org"
        urls = extract_urls(text)

        assert len(urls) == 2

    @pytest.mark.unit
    def test_extract_urls_returns_empty_for_no_urls(self):
        """Should return empty list when no URLs found"""
        from agent.agno_agent.tools.url_reader import extract_urls

        text = "This is a message without any URLs"
        urls = extract_urls(text)

        assert urls == []


class TestExtractTitleFromMarkdown:
    """Tests for title extraction from Jina Reader markdown"""

    @pytest.mark.unit
    def test_extract_title_from_title_prefix(self):
        """Should extract title from 'Title: xxx' format"""
        from agent.agno_agent.tools.url_reader import _extract_title_from_markdown

        content = "Title: My Page Title\n\nSome content here"
        title = _extract_title_from_markdown(content)

        assert title == "My Page Title"

    @pytest.mark.unit
    def test_extract_title_from_h1(self):
        """Should extract title from '# xxx' format"""
        from agent.agno_agent.tools.url_reader import _extract_title_from_markdown

        content = "# My Page Title\n\nSome content here"
        title = _extract_title_from_markdown(content)

        assert title == "My Page Title"

    @pytest.mark.unit
    def test_extract_title_returns_none_when_missing(self):
        """Should return None when no title found"""
        from agent.agno_agent.tools.url_reader import _extract_title_from_markdown

        content = "Just some content without a title"
        title = _extract_title_from_markdown(content)

        assert title is None

    @pytest.mark.unit
    def test_extract_title_handles_empty_content(self):
        """Should handle empty content"""
        from agent.agno_agent.tools.url_reader import _extract_title_from_markdown

        title = _extract_title_from_markdown("")
        assert title is None


class TestUrlContent:
    """Tests for UrlContent dataclass"""

    @pytest.mark.unit
    def test_url_content_to_dict(self):
        """Should convert to dict correctly"""
        from agent.agno_agent.tools.url_reader import UrlContent

        uc = UrlContent(
            url="https://example.com",
            title="Example",
            content="Hello world",
            error=None,
        )
        result = uc.to_dict()

        assert result["url"] == "https://example.com"
        assert result["title"] == "Example"
        assert result["content"] == "Hello world"
        assert result["error"] is None


class TestFetchUrlContent:
    """Tests for URL fetching via Jina Reader"""

    @pytest.mark.unit
    def test_fetch_url_content_success(self):
        """Should fetch content via Jina Reader"""
        from agent.agno_agent.tools.url_reader import fetch_url_content

        mock_response = MagicMock()
        mock_response.text = "Title: Test Page\n\nThis is the content."

        with patch("agent.agno_agent.tools.url_reader.httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = (
                mock_response
            )

            result = fetch_url_content("https://example.com")

            assert result.url == "https://example.com"
            assert result.title == "Test Page"
            assert "This is the content" in result.content
            assert result.error is None

            # Verify Jina Reader URL was called
            mock_client.return_value.__enter__.return_value.get.assert_called_once()
            call_args = mock_client.return_value.__enter__.return_value.get.call_args
            assert "r.jina.ai" in call_args[0][0]

    @pytest.mark.unit
    def test_fetch_url_content_timeout(self):
        """Should handle timeout gracefully"""
        import httpx

        from agent.agno_agent.tools.url_reader import fetch_url_content

        with patch("agent.agno_agent.tools.url_reader.httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.side_effect = (
                httpx.TimeoutException("timeout")
            )

            result = fetch_url_content("https://example.com")

            assert result.url == "https://example.com"
            assert result.error == "Request timeout"
            assert result.content == ""

    @pytest.mark.unit
    def test_fetch_url_content_truncates_long_content(self):
        """Should truncate content exceeding max length"""
        from agent.agno_agent.tools.url_reader import fetch_url_content

        long_content = "x" * 5000
        mock_response = MagicMock()
        mock_response.text = long_content

        with patch("agent.agno_agent.tools.url_reader.httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = (
                mock_response
            )

            result = fetch_url_content("https://example.com", max_length=100)

            assert len(result.content) < 150  # 100 + truncation message
            assert "[内容已截断...]" in result.content


class TestFormatUrlContext:
    """Tests for URL context formatting"""

    @pytest.mark.unit
    def test_format_url_context_with_content(self):
        """Should format URL content correctly"""
        from agent.agno_agent.tools.url_reader import UrlContent, format_url_context

        contents = [
            UrlContent(url="https://example.com", title="Example", content="Hello"),
        ]
        result = format_url_context(contents)

        assert "### 链接内容" in result
        assert "https://example.com" in result
        assert "Example" in result
        assert "Hello" in result

    @pytest.mark.unit
    def test_format_url_context_with_error(self):
        """Should format error message correctly"""
        from agent.agno_agent.tools.url_reader import UrlContent, format_url_context

        contents = [
            UrlContent(url="https://example.com", error="Connection failed"),
        ]
        result = format_url_context(contents)

        assert "无法获取" in result
        assert "Connection failed" in result

    @pytest.mark.unit
    def test_format_url_context_empty_list(self):
        """Should return empty string for empty list"""
        from agent.agno_agent.tools.url_reader import format_url_context

        result = format_url_context([])

        assert result == ""
