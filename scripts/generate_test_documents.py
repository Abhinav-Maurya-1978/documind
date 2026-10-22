import os
from pathlib import Path
import pymupdf

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"

def create_pdf(file_path: Path, pages_content: list[str]):
    """Creates a synthetic PDF with specified text per page."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()
    for text in pages_content:
        page = doc.new_page(width=595, height=842)  # A4 standard
        # Insert text at top
        rect = pymupdf.Rect(50, 50, 545, 792)
        page.insert_textbox(rect, text, fontsize=11, fontname="helv", align=0)
    doc.save(str(file_path))
    doc.close()
    print(f"Generated test document: {file_path}")

def generate_all_fixtures():
    """Generates synthetic procurement document fixtures for testing and evaluation."""
    # Pair A: Classic Monetary & Deadline Contradiction with Consistent Equivalent Date
    po_101_text = """
    PURCHASE ORDER: PO-101
    Vendor ID: VEND-8890
    Tax ID: GSTIN07AAAAA0000A1Z5
    Order Date: 01/02/2026

    Items Ordered:
    Item 1: 10 Laptops @ Rs. 5,000 each.

    Delivery Terms:
    Delivery within 30 days from order confirmation.

    Financial Summary:
    Total Amount: Rs. 50,000 INR
    Payment Terms: Net 30 days upon invoice receipt.
    """

    inv_101_text = """
    TAX INVOICE: INV-101
    Reference PO Number: PO-101
    Invoice Date: February 1, 2026

    Billing Line Items:
    10 Laptops delivered to client warehouse.

    Delivery Execution:
    Delivery within 45 days of manufacturing schedule.

    Payment Information:
    Grand Total: Rs. 55,000 INR
    Please transfer payable balance immediately.
    """

    create_pdf(OUTPUT_DIR / "PO_101.pdf", [po_101_text])
    create_pdf(OUTPUT_DIR / "INV_101.pdf", [inv_101_text])

    # Pair B: Different Line Items (Harmless difference) & Quantities
    po_102_text = """
    PURCHASE ORDER: PO-102
    Customer: Global Tech Corp
    Order Date: 15/03/2026

    Order Specification:
    Line Item A: 10 Laptops
    Total Amount: $5,000 USD
    """

    quote_102_text = """
    SUPPLIER QUOTATION: QUOTE-102
    Related PO: PO-102
    Quote Date: 15/03/2026

    Proposed Peripherals:
    Line Item B: 20 Monitors
    Total Amount: $5,000 USD
    """

    create_pdf(OUTPUT_DIR / "PO_102.pdf", [po_102_text])
    create_pdf(OUTPUT_DIR / "QUOTE_102.pdf", [quote_102_text])

    # Pair C: Currency Mismatch & Missing Tax Information
    contract_103_text = """
    MASTER SERVICE AGREEMENT: MSA-103
    Tax ID: US-EIN-992144
    Agreement Date: 2026-05-10
    Total Payable: $500 USD
    Payment Terms: Net 15 days
    """

    invoice_103_text = """
    INVOICE: INV-103
    Agreement Reference: MSA-103
    Invoice Date: 2026-05-10
    Total Payable: ₹500 INR
    Payment Terms: Net 15 days
    """

    create_pdf(OUTPUT_DIR / "CONTRACT_103.pdf", [contract_103_text])
    create_pdf(OUTPUT_DIR / "INVOICE_103.pdf", [invoice_103_text])

    # Pair D: Identical Consistent Multi-Page Agreement
    page1_contract = """
    STRATEGIC PARTNERSHIP CONTRACT: PART-200
    Page 1 of 2
    Vendor ID: VEND-4411
    Effective Date: 2026-01-15
    Tax ID: GSTIN27BBBBB1111B2Z3
    Total Amount: Rs. 1,50,000 INR
    """
    page2_contract = """
    STRATEGIC PARTNERSHIP CONTRACT: PART-200
    Page 2 of 2
    Delivery Deadline: 60 days
    Obligation: Vendor shall deliver all hardware to headquarters.
    """

    page1_confirm = """
    ORDER CONFIRMATION: CONF-200
    Page 1 of 2
    Contract Ref: PART-200
    Vendor ID: VEND-4411
    Effective Date: 2026-01-15
    Total Amount: Rs. 1,50,000 INR
    """
    page2_confirm = """
    ORDER CONFIRMATION: CONF-200
    Page 2 of 2
    Delivery Deadline: 60 days
    Obligation: Deliveries confirmed according to schedule.
    """

    create_pdf(OUTPUT_DIR / "PARTNERSHIP_200.pdf", [page1_contract, page2_contract])
    create_pdf(OUTPUT_DIR / "CONFIRMATION_200.pdf", [page1_confirm, page2_confirm])

    print("All synthetic test documents generated successfully in:", OUTPUT_DIR)

if __name__ == "__main__":
    generate_all_fixtures()
