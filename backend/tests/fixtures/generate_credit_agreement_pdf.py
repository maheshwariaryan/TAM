"""Generate a digital (text-extractable) credit agreement PDF fixture.

Terms are intentionally distinctive so tests can prove the parser is reading
the PDF text rather than inventing hardcoded mock values.
"""

from pathlib import Path

import fitz  # pymupdf

FIXTURES = Path(__file__).parent
OUT = FIXTURES / "Credit_Agreement_FNB.pdf"

# Canonical terms asserted by tests — keep in sync with contract parser expectations.
LENDER = "Horizon Commercial Bank"
FACILITY = "Senior Secured Term Loan"
PRINCIPAL = "$7,500,000.00"
RATE = "7.85%"
MATURITY = "December 15, 2029"
BORROWER = "Acme Manufacturing LLC"
COVENANTS = (
    "Maximum Net Leverage Ratio of 3.25x EBITDA; "
    "Minimum Interest Coverage Ratio of 2.00x; "
    "quarterly financial reporting required within 45 days of quarter end."
)

AGREEMENT_TEXT = f"""
CREDIT AGREEMENT

This Credit Agreement (the "Agreement") is entered into as of January 10, 2024,
by and between {BORROWER} (the "Borrower") and {LENDER} (the "Lender").

ARTICLE I — FACILITY TERMS

Facility Type: {FACILITY}
Lender: {LENDER}
Borrower: {BORROWER}
Principal Outstanding: {PRINCIPAL}
Interest Rate: {RATE} per annum, payable quarterly in arrears
Maturity Date: {MATURITY}

ARTICLE II — FINANCIAL COVENANTS

The Borrower shall maintain the following financial covenants:
{COVENANTS}

ARTICLE III — EVENTS OF DEFAULT

Failure to pay principal or interest when due, or breach of any financial
covenant set forth in Article II, shall constitute an Event of Default.

ARTICLE IV — CHANGE OF CONTROL

Upon a Change of Control of the Borrower, the Lender may declare all outstanding
Obligations immediately due and payable, and the Borrower shall provide the
Lender not less than 30 days' prior written notice of any such Change of Control.

ARTICLE V — PREPAYMENT

The Borrower may voluntarily prepay the Loan in whole or in part at any time
upon 5 business days' notice, subject to a prepayment premium of 1.00% of the
amount prepaid if such prepayment occurs prior to the first anniversary of
this Agreement.

ARTICLE VI — AFFIRMATIVE COVENANTS

The Borrower shall: (i) maintain insurance on all collateral in amounts
satisfactory to Lender; (ii) deliver audited annual financial statements
within 90 days of fiscal year end; (iii) promptly notify Lender of any
material litigation or default.

IN WITNESS WHEREOF, the parties have executed this Agreement as of the date first written above.
""".strip()


def _fits(rect: "fitz.Rect", text: str) -> bool:
    """Check (on a throwaway page) whether text fits the textbox without rendering it for real.

    Calling insert_textbox twice on the *same* real page (once to test, once for real) draws
    the text twice at overlapping positions, corrupting extracted text — so measurement must
    happen on a disposable page/document.
    """
    scratch_doc = fitz.open()
    try:
        scratch_page = scratch_doc.new_page(width=612, height=792)
        rc = scratch_page.insert_textbox(rect, text, fontsize=11, fontname="helv", align=fitz.TEXT_ALIGN_LEFT)
        return rc >= 0
    finally:
        scratch_doc.close()


def generate(path: Path = OUT) -> Path:
    rect = fitz.Rect(54, 54, 558, 738)

    # Paginate: paragraphs are separated by blank lines. Grow a buffer paragraph-by-paragraph,
    # measuring fit on a scratch page each time, and only render the final per-page text once
    # a single insert_textbox call per real page.
    paragraphs = AGREEMENT_TEXT.split("\n\n")
    pages_text: list[str] = []
    buffer = ""
    for para in paragraphs:
        candidate = f"{buffer}\n\n{para}" if buffer else para
        if _fits(rect, candidate):
            buffer = candidate
        else:
            if buffer:
                pages_text.append(buffer)
            buffer = para
    if buffer:
        pages_text.append(buffer)

    doc = fitz.open()
    for page_text in pages_text:
        page = doc.new_page(width=612, height=792)  # US Letter
        page.insert_textbox(rect, page_text, fontsize=11, fontname="helv", align=fitz.TEXT_ALIGN_LEFT)
    doc.save(path)
    doc.close()
    return path


if __name__ == "__main__":
    out = generate()
    print(f"Written {out}")
