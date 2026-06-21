import os
from bs4 import BeautifulSoup

def extract_curriculum():
    input_filename = "page_file.txt"
    output_path = os.path.join("..", "curriculum.txt")

    try:
        with open(input_filename, "r", encoding="utf-8") as f:
            html_content = f.read()
    except FileNotFoundError:
        print(f"Error: '{input_filename}' not found.")
        return

    soup = BeautifulSoup(html_content, "html.parser")
    buttons = soup.find_all("button", class_="contents-thumb")
    
    if not buttons:
        print("No items found. Check your HTML container structure.")
        return

    with open(output_path, "w", encoding="utf-8") as out_file:
        for idx, btn in enumerate(buttons, start=1):
            title = btn.get("data-title", "").strip()
            
            # Find the parent module section name dynamically
            parent_section = btn.find_parent("section", class_="contents-module")
            if parent_section:
            # Dynamically extract the text from the <h3> element (e.g., "Unit 2: Family")
                h3_tag = parent_section.find("h3")
                if h3_tag:
                    module_name = h3_tag.get_text(strip=True)
                else:
                    # Fallback if no <h3> is found inside the section
                    module_id = parent_section.get("id", "module-1").replace("module-", "Unit ")
                    module_name = f"{module_id}: Unknown Unit"
            else:
                module_name = "No section Found"

            # Construct the exact static video link using the title
            video_link = f"https://vistasl.eelvex.net/static/vid/teacher-video-{title}.mp4"

            # Write matching your template format
            out_file.write("---\n")
            out_file.write(f"LESSON_ID: {idx}\n")
            out_file.write(f"TITLE: {title}\n")
            out_file.write(f"MODULE: {module_name}\n")
            out_file.write(f"LINK: {video_link}\n")
            
        out_file.write("---\n")

    print(f"Successfully formatted and saved to: {os.path.abspath(output_path)}")

if __name__ == "__main__":
    extract_curriculum()