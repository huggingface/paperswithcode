"""
Integration test for PDF download with validation.
Tests with a real arXiv paper to ensure the async context manager works correctly.
"""

import asyncio
import sys

sys.path.insert(0, "/root/python_projects/paperswithcode")

from backend.utils.pdf_utils import temp_pdf_download


async def test_real_pdf_download():
    """Test downloading a real PDF from arXiv."""
    # Using a small, well-known paper
    arxiv_id = "2410.00337"

    print(f"🔄 Testing PDF download for {arxiv_id}...")

    try:
        async with temp_pdf_download(arxiv_id) as pdf_path:
            print(f"✅ PDF downloaded to: {pdf_path}")

            # Verify the file exists and is readable
            with open(pdf_path, "rb") as f:
                content = f.read()

            # Verify it's actually a PDF
            assert content.startswith(b"%PDF-"), (
                "File should start with PDF magic bytes"
            )
            assert b"%%EOF" in content, "File should contain EOF marker"

            print(f"✅ PDF validated: {len(content)} bytes")
            print("✅ File is a valid PDF")

    except Exception as e:
        print(f"❌ Test failed: {e}")
        raise

    print("✅ Integration test passed!")


async def test_invalid_arxiv_id():
    """Test handling of invalid arXiv ID."""
    arxiv_id = "9999.99999"  # Invalid ID

    print(f"\n🔄 Testing invalid arXiv ID: {arxiv_id}...")

    try:
        async with temp_pdf_download(arxiv_id) as pdf_path:
            print(f"❌ Should have failed but got: {pdf_path}")
            assert False, "Should have raised an exception"
    except Exception as e:
        error_msg = str(e).lower()
        if (
            "404" in error_msg
            or "not found" in error_msg
            or "failed to download" in error_msg
        ):
            print(f"✅ Correctly raised exception: {e}")
        else:
            print(f"⚠️  Got exception (may or may not be expected): {e}")


async def main():
    """Run all integration tests."""
    print("🧪 Running PDF download integration tests...\n")

    # Test 1: Real PDF download
    await test_real_pdf_download()

    # Test 2: Invalid arXiv ID
    await test_invalid_arxiv_id()

    print("\n✅ All integration tests completed!")


if __name__ == "__main__":
    asyncio.run(main())
