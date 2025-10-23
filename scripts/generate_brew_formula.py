#!/usr/bin/env python3
"""Generate Homebrew formula for CLI AI Coder from PyPI."""

import hashlib
import json
import sys
from urllib.request import urlopen


def get_latest_release():
    """Get latest release info from PyPI."""
    url = "https://pypi.org/pypi/cli-ai-coder/json"
    try:
        with urlopen(url) as response:
            data = json.load(response)
        version = data["info"]["version"]
        releases = data["releases"][version]
        # Find wheel
        wheel = None
        for release in releases:
            if release["packagetype"] == "bdist_wheel" and "py3" in release["filename"]:
                wheel = release
                break
        if not wheel:
            raise ValueError("No wheel found")
        return version, wheel["url"], wheel["digests"]["sha256"]
    except Exception as e:
        print(f"Error fetching PyPI data: {e}", file=sys.stderr)
        sys.exit(1)


def generate_formula(version, url, sha256):
    """Generate Homebrew formula."""
    formula = f'''class CliAiCoder < Formula
  include Language::Python::Virtualenv

  desc "CLI AI Coder with xAI integration"
  homepage "https://github.com/yourusername/cli-ai-coder"
  url "{url}"
  sha256 "{sha256}"
  license "MIT"

  depends_on "python@3.10"

  def install
    virtualenv_install_with_resources
  end

  test do
    system bin/"ccode", "--help"
  end
end
'''
    return formula


def main():
    version, url, sha256 = get_latest_release()
    formula = generate_formula(version, url, sha256)
    print(formula)


if __name__ == "__main__":
    main()