import json
import os
import fitz  # PyMuPDF

def extract_pdf_to_json(pdf_path, json_path):
    print(f"Reading PDF: {pdf_path}...")
    try:
        doc = fitz.open(pdf_path)
        pages_data = []
        
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            text = page.get_text()
            
            pages_data.append({
                "page": page_num + 1,
                "content": text.strip()
            })
            
        json_data = {
            "document_name": os.path.basename(pdf_path),
            "total_pages": len(doc),
            "pages": pages_data
        }
        
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=4)
            
        print(f"Successfully converted PDF to JSON! Saved at: {json_path}")
        
    except Exception as e:
        print(f"Error extracting PDF: {e}")

if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    pdf_file = os.path.join(current_dir, "data", "ip", "gi_act_1999.pdf.pdf")
    json_file = os.path.join(current_dir, "data", "ip", "gi_act_1999.json")
    
    if os.path.exists(pdf_file):
        extract_pdf_to_json(pdf_file, json_file)
    else:
        print(f"PDF file not found at: {pdf_file}")
