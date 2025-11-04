import google.generativai as genai
import pandas as pd
import os
import json
import math
import time
import streamlit as st # Thêm Streamlit
import re # Thêm thư viện Regex để phân tích Markdown

# --- API KEY CONFIGURATION ---
try:
    # Thử lấy key từ Streamlit Secrets trước (CHO REPLIT)
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
except (FileNotFoundError, KeyError):
    # Nếu không, thử lấy từ Biến Môi trường (nếu chạy local)
    try:
        GOOGLE_API_KEY = os.environ["GOOGLE_API_KEY"]
    except KeyError:
        # Nếu không, dùng key hardcode (cho local dev)
        GOOGLE_API_KEY = "YOUR_NEW_API_KEY" # ⚠️ Dán key của bạn vào đây nếu không dùng secrets

try:
    genai.configure(api_key=GOOGLE_API_KEY)
except Exception as e:
    st.error(f"Error configuring API Key: {e}. Please check your API key.")
    st.stop() # Dừng ứng dụng nếu key lỗi

# Select the model
model = genai.GenerativeModel('gemini-2.5-flash')
# -------------------------

def call_gemini_api(prompt, is_json=False):
    """
    Helper function to call the API and handle errors
    """
    st.info(f"   ... 🤖 Sending request to AI (Model: {model.model_name})...")
    
    try:
        if is_json:
            prompt_full = f"{prompt}\n\nPlease respond with only a valid JSON string (or a JSON list). Do not add any other text, explanations, or markdown."
        else:
            prompt_full = prompt
            
        response = model.generate_content(prompt_full)
        
        # Giữ thời gian chờ để tránh lỗi quota
        time.sleep(2) 
        
        text_response = response.text.strip()
        if is_json and text_response.startswith("```json"):
            text_response = text_response[7:-3].strip() # Remove ```json and ```
        
        return text_response
    except Exception as e:
        st.warning(f"   --- 😥 Error calling API: {e} ---")
        st.warning("   --- Will retry after 5 seconds ---")
        time.sleep(5)
        # Retry once
        try:
            response = model.generate_content(prompt_full)
            time.sleep(2)
            text_response = response.text.strip()
            if is_json and text_response.startswith("```json"):
                text_response = text_response[7:-3].strip() # Remove ```json and ```
            return text_response
        except Exception as e2:
            st.error(f"   --- 😥 Error on second try: {e2}. Skipping this step. ---")
            return None # Return None on failure

# --- [NEW] HÀM PHÂN TÍCH BẢNG MARKDOWN ---
def parse_markdown_table(markdown_text):
    """
    Trích xuất dữ liệu từ bảng Markdown trong kịch bản.
    """
    parsed_scenes = []
    # Biểu thức chính quy (Regex) để tìm các hàng trong bảng
    # | Timecode | Scene Description | Camera Angle | Sound/Ambience | Emotion |
    table_regex = re.compile(
        r"\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|"
    )
    
    table_found = False
    for line in markdown_text.split('\n'):
        line = line.strip()
        
        # Bỏ qua header
        if "Timecode" in line and "Scene Description" in line:
            table_found = True
            continue
        # Bỏ qua dòng phân cách "---"
        if "---" in line and table_found:
            continue
        # Bắt đầu phân tích các hàng
        if table_found and line.startswith('|'):
            match = table_regex.match(line)
            if match:
                groups = match.groups()
                if len(groups) == 5:
                    parsed_scenes.append({
                        "timecode": groups[0],
                        "description": groups[1],
                        "camera": groups[2],
                        "sound": groups[3],
                        "emotion": groups[4]
                    })
                    
    return parsed_scenes

# --- [NEW] HÀM PHÂN TÍCH CÁC PHẦN KHÁC ---
def parse_script_sections(markdown_text):
    """
    Trích xuất Tiêu đề, Mô tả, Thumbnail Prompts, etc.
    """
    data = {}
    try:
        # Dùng Regex để tìm các phần (rất linh hoạt)
        data['title'] = re.search(r"#\s*Title\s*\n(.*?)\n", markdown_text, re.DOTALL | re.IGNORECASE).group(1).strip()
    except: data['title'] = "Title Not Found"
    
    try:
        data['description'] = re.search(r"#\s*Description\s*\n(.*?)\n#", markdown_text, re.DOTALL | re.IGNORECASE).group(1).strip()
    except: data['description'] = "Description Not Found"

    # Đã thêm regex cho Hashtags
    try:
        data['hashtags'] = re.search(r"#\s*Hashtags\s*\n(.*?)\n#", markdown_text, re.DOTALL | re.IGNORECASE).group(1).strip()
    except: data['hashtags'] = "#hashtags #not #found"
    
    try:
        data['thumbnail_prompts'] = re.search(r"#\s*Thumbnail Prompts\s*\n(.*?)\n#", markdown_text, re.DOTALL | re.IGNORECASE).group(1).strip()
    except: data['thumbnail_prompts'] = "Thumbnails Not Found"

    try:
        data['keywords'] = re.search(r"#\s*Keywords\s*\n(.*?)\n#", markdown_text, re.DOTALL | re.IGNORECASE).group(1).strip()
    except: data['keywords'] = "Keywords Not Found"
    
    return data

# --- LOGIC CHÍNH (Đã được cập nhật) ---
def main_automation(video_topic, video_duration_minutes):
    
    # Placeholder cho các thanh status
    status_area = st.container()
    progress_bar = status_area.progress(0, text="Starting...")
    SCENE_DURATION_SECONDS = 8 # Mặc định
    JSON_BATCH_SIZE = 10 
    
    # Tính toán tổng số cảnh
    total_scenes = math.ceil((video_duration_minutes * 60) / SCENE_DURATION_SECONDS)
    st.info(f"Calculating for {video_duration_minutes} minutes... ({total_scenes} scenes @ {SCENE_DURATION_SECONDS}s each)")

    try:
        # --- [STEP 1] (Đã Nâng cấp): GENERATE "PREHUMANFILE" SCRIPT ---
        progress_bar.progress(10, text="[1/5] Generating 'PrehumanFile' master script...")
        
        prompt_task_1_prehumanfile = f"""
        You are a cinematic scriptwriter for the YouTube channel “PrehumanFile,” which produces visually immersive, emotional, AI-generated documentaries about prehistoric survival.  
        
        Your task: Write a full cinematic script (VEO 3–ready format) for one episode based on the user’s provided video topic and duration.

        === INPUT ===
        Video Topic: "{video_topic}"
        Video Duration: "{video_duration_minutes} minutes"

        === OUTPUT STYLE & STRUCTURE ===

        🎯 1. VIDEO OVERVIEW
        - Title suggestion (fit YouTube style: “Life X Million Years Ago | [Conflict/Emotion/Outcome]”)
        - One-line tagline
        - Short description (SEO-optimized, cinematic tone)
        - Recommended hashtags (#prehistoric #prehumanfile #survival #stoneage #ancienthumans)

        🎬 2. CINEMATIC SCRIPT STRUCTURE ({video_duration_minutes} minutes total)
        Divide into 3 ACTS and a CLOSING TAG.
        Your script table must contain exactly {total_scenes} scenes.
        
        | Timecode | Scene Description (1 line, cinematic) | Camera Angle | Sound/Ambience | Emotion |
        |-----------|----------------------------------------|----------------|----------------|----------|

        Follow this model:
        - **Act I – Awakening (10% duration):** Introduce environment + first instinct (fear or awe).
        - **Act II – Confrontation (60% duration):** Main survival conflict: danger, strategy, or loss.
        - **Act III – Resolution (25% duration):** Survival outcome, emotional reflection.
        - **Tag Scene (5% duration):** A haunting or hopeful visual to tease the next episode.

        Each scene = one {SCENE_DURATION_SECONDS}s micro-shot (for VEO 3 input).  
        Use compact English (one line per scene, no line breaks inside).  

        🎥 3. CINEMATIC VISUAL GUIDELINES
        - **Scientific Consistency:** You MUST define the specific prehistoric era (e.g., Late Pleistocene) and hominid species (e.g., Neanderthal, Homo erectus) based on the topic.
        - **Mandatory Consistency:** All animals, plants, and tools mentioned MUST be scientifically accurate for that specific era and species.
        - Aspect ratio 16:9, golden-hour or storm lighting, Panavision anamorphic lens.
        - Focus on prehistoric realism: stone tools, mammoths, volcano smoke, tribal faces.
        - Lighting tone: fire-orange, fog-blue, or earthy neutrals.
        - Human motion should feel natural, grounded, emotional (close-ups on eyes, hands, fire).

        🔊 4. AUDIO & ATMOSPHERE
        - Ambient base: wind, crackling fire, breathing, animal calls.
        - Emotional layer: deep tribal drums, low strings, heartbeat pulse.
        - Use silence strategically (before climax or aftermath).
        - Sound motif: final 2 seconds = “flame burst + deep drum” (brand signature).

        💥 5. HOOK & CTA
        - First 8 seconds: visual shock or emotional hook (“Fear → Curiosity → Survival”).
        - Add one text overlay hook at 0:05 like: “When fire dies, how do you survive the night?”
        - CTA end-screen line: “Continue the PrehumanFile — next chapter below 🔥”.

        📜 6. ADDITIONAL OUTPUTS
        - 3 alternative YouTube titles (SEO-friendly + emotionally charged)
        - 3 highly detailed, 50-word cinematic thumbnail prompts (for AI image generation)
        - 5 SEO keywords related to the episode
        - Short caption (for YouTube Shorts version, <100 characters)

        === OUTPUT FORMAT ===
        Return everything as clear Markdown sections:
        # Title
        (Suggested Title)

        # Description
        (Tagline and Description)
        
        # Hashtags
        (Hashtags)
        
        # Era Definition
        (e.g., "Era: Late Pleistocene. Species: Homo neanderthalensis")

        # Script (table format)
        (The full Markdown table with exactly {total_scenes} scenes)
        
        # Thumbnail Prompts
        (3 prompt lines)

        # Keywords
        (5 keywords)

        # CTA
        (CTA Line and Hook Text)

        Tone: cinematic, emotional, survival-driven, with a mythic prehistoric atmosphere.
        """
        markdown_script = call_gemini_api(prompt_task_1_prehumanfile)
        if not markdown_script:
            st.error("Error: Could not generate master script. Exiting.")
            return

        # Hiển thị toàn bộ kịch bản Markdown lên giao diện
        with st.expander("Show Generated Master Script (Markdown)", expanded=True):
            st.markdown(markdown_script)
        
        # --- [STEP 2] (Đã Nâng cấp): PARSE MARKDOWN SCRIPT ---
        progress_bar.progress(25, text="[2/5] Parsing generated script...")
        
        # Phân tích bảng
        scene_list_data = parse_markdown_table(markdown_script)
        
        if not scene_list_data:
             st.error("   ! Critical Error: AI did not return a valid Markdown Table for the script. Stopping.")
             return
        
        num_scenes_generated = len(scene_list_data)
        if num_scenes_generated != total_scenes:
             st.warning(f"   ! Warning: AI generated {num_scenes_generated} scenes instead of {total_scenes} as requested. Continuing.")
        else:
             status_area.info(f"   -> Parsed a total of {num_scenes_generated} scenes from Markdown table.")
        
        # Phân tích các phần khác (Tiêu đề, Mô tả...)
        other_script_data = parse_script_sections(markdown_text)
        st.text_input("Generated Title", value=other_script_data.get('title', ''))
        st.text_area("Generated Description", value=other_script_data.get('description', ''))
        st.text_area("Generated Thumbnail Prompts", value=other_script_data.get('thumbnail_prompts', ''))
        
        # Hiển thị bảng dữ liệu
        st.dataframe(pd.DataFrame(scene_list_data))

        # --- [MỚI] TẠO VÀ TẢI VỀ TỆP METADATA .TXT ---
        try:
            metadata_content = f"""
# ===============================
# PREHUMANFILE VIDEO METADATA
# ===============================

# TITLE
{other_script_data.get('title', 'N/A')}

# DESCRIPTION
{other_script_data.get('description', 'N/A')}

# HASHTAGS
{other_script_data.get('hashtags', 'N/A')}

# KEYWORDS
{other_script_data.get('keywords', 'N/A')}

# THUMBNAIL PROMPTS
{other_script_data.get('thumbnail_prompts', 'N/A')}
            """
            
            st.download_button(
                label="Download Video Metadata (.txt)",
                data=metadata_content.strip(),
                file_name="video_metadata.txt",
                mime="text/plain"
            )
        except Exception as e:
            st.warning(f"Could not generate metadata download button: {e}")
        # --- KẾT THÚC BƯỚC MỚI ---
        
        # --- [STEP 3] (Đã Nâng cấp): GENERATE CONSISTENCY KEYS ---
        progress_bar.progress(40, text="[3/5] Generating Consistency Keys...")
        prompt_task_2_5 = f"""
        Based on the following full master script: 
        "{markdown_script}"
        
        Identify the MAIN CHARACTERS, KEY LOCATIONS, or special OBJECTS that will appear repeatedly.
        For each item, provide a detailed visual description to ensure consistency in all scenes.
        Pay close attention to the "Era Definition" (Species, Era) from the script.

        Example:
        - CHARACTER (Kael): 'A young Neanderthal hunter, lean, wearing rough furs, has a scar over
        his left eye, carries a flint-tipped spear. (Based on Homo neanderthalensis)'
        - LOCATION (The Valley): 'A misty, volcanic valley, black rock, sparse giant ferns (Pleistocene era), a river of slow-moving lava in the distance.'

        Please respond concisely, focusing on visual descriptions.
        Please respond in English.
        """
        consistency_keys = call_gemini_api(prompt_task_2_5)
        if not consistency_keys:
            st.warning("   ! Warning: Could not generate consistency keys. Continuing without them.")
            consistency_keys = "None"
            
        with st.expander("Show Generated Consistency Keys"):
            st.markdown(consistency_keys)

        # --- [STEP 4] (Đã Nâng cấp): GENERATE VEO 3 JSON PROMPT (IN BATCHES) ---
        progress_bar.progress(60, text="[4/5] Processing JSON details in batches...")
        
        all_scenes_data = [] # Đây là danh sách cuối cùng cho Excel
        
        # Template JSON Veo 3 (từ file Prompt AI Veo 3.txt của bạn)
        json_template_string = f"""
        {{
            "1. CORE_IDEA": {{
                "scene_purpose": "Briefly describe the purpose of this scene (based on the scene description)",
                "desired_duration_seconds": {SCENE_DURATION_SECONDS}
            }},
            "2. CHARACTERS_AND_ACTIONS": [
                {{
                    "character": "Character Name 1 (if any, use name from consistency keys)",
                    "description": "Appearance description (TAKE FROM CONSISTENCY KEYS IF AVAILABLE)",
                    "action_and_expression": "Describe the specific action and expression IN THIS SCENE"
                }}
            ],
            "3. SETTING": {{
                "location": "Location (TAKE FROM CONSISTENCY KEYS IF AVAILABLE, or describe new)",
                "time_and_weather": "Time of day and weather in this scene",
                "key_elements": ["Key Element 1", "Key Element 2", "Key Element 3"],
                "negative_prompt": "cartoon, animated, stylized, illustration, low-resolution, blurry, morphing artifacts, distorted features, unrealistic movement, fast motion, shaky cam, text, watermark, humans, man-made objects, modern technology, grass, flowering plants, mammals, incorrect anatomy, unrealistic physics, gore, blood."
            }},
            "4. VISUAL_STYLE_AND_MOOD": {{
                "film_genre": "Science Fiction",
                "primary_mood": "The primary mood or atmosphere (e.g., 'Mystical', 'Joyful', 'Mysterious and tense')",
                "lighting_and_color": "Description of lighting and dominant colors (e.g., 'Soft lighting, pastel tones', 'High contrast, neon colors')",
                "camera_work": "Description of camera techniques (e.g., 'Low angle shot', 'Handheld camera')"
            }},
            "5. AUDIO": {{
                "background_music": "Type of background music (e.g., 'Epic orchestral score', 'Gentle lo-fi music')",
                "ambient_sound": "A rich, layered description of the soundscape (e.g., 'the buzz of prehistoric insects, distant calls of unknown creatures')",
                "sound_effects": ["Sound Effect 1 (e.g., 'deep footfalls')", "Sound Effect 2 (e.g., 'a low growl')"]
            }}
        }}
        """
        
        # Lặp qua danh sách cảnh (đã được phân tích) theo từng lô (batch)
        num_batches = math.ceil(len(scene_list_data) / JSON_BATCH_SIZE)
        for i in range(0, len(scene_list_data), JSON_BATCH_SIZE):
            
            batch_num = (i // JSON_BATCH_SIZE) + 1
            progress_bar.progress(60 + int(batch_num * (35/num_batches)), text=f"[4/5] Processing JSON batch {batch_num}/{num_batches}...")

            batch_of_scenes_data = scene_list_data[i:i + JSON_BATCH_SIZE]
            
            # Xây dựng chuỗi thông tin đầu vào cho batch này
            batch_input_string = ""
            for j, scene_data in enumerate(batch_of_scenes_data):
                scene_num = i + 1 + j
                batch_input_string += f"--- SCENE {scene_num} INPUT ---\n"
                batch_input_string += f"Timecode: {scene_data['timecode']}\n"
                batch_input_string += f"Description: {scene_data['description']}\n"
                batch_input_string += f"Camera: {scene_data['camera']}\n"
                batch_input_string += f"Sound: {scene_data['sound']}\n"
                batch_input_string += f"Emotion: {scene_data['emotion']}\n\n"

            # --- Tạo prompt NÂNG CẤP cho batch 4 ---
            prompt_task_4_batch = f"""
            You are a JSON generation bot.
            You will be given a list of structured scene inputs (from a Markdown table) and consistency keys.
            You MUST return a valid JSON LIST, containing one JSON object for each scene,
            filled according to the JSON TEMPLATE.
            
            CONSISTENCY KEYS (MUST ADHERE IF RELEVANT):
            "{consistency_keys}"

            JSON TEMPLATE (Use this for each object in the list):
            {json_template_string}
            
            STRUCTURED SCENE INPUTS (Generate one JSON object for each):
            {batch_input_string}
            ---

            INSTRUCTIONS:
            Fill in the JSON TEMPLATE for EACH of the {len(batch_of_scenes_data)} scenes provided above.
            
            - **action_and_expression**: THIS IS CRITICAL. EXPAND the 1-line input "Description" (e.g., "Kael watches the herd") into a detailed, 300-400 word cinematic description of the action, character expression, and environment for this specific scene. Be vivid and immersive.
            - "scene_purpose": Base this on the input "Description".
            - "camera_work": Use the input "Camera" (e.g., "Close-up")
            - "primary_mood": Use the input "Emotion" (e.g., "Terror")
            - "ambient_sound": Use the input "Sound" (e.g., "Roar, rain")
            - "character" / "description" / "location": Use the CONSISTENCY KEYS.
            - "negative_prompt": MUST be kept exactly as it is.

            Respond with only a valid JSON LIST (e.g., [ {{...}}, {{...}}, ... ]).
            """
            
            json_response_string = call_gemini_api(prompt_task_4_batch, is_json=True)
            
            if not json_response_string:
                st.warning(f"   ! Error: No response received for batch {batch_num}. Skipping batch.")
                continue 

            # --- Xử lý danh sách JSON ---
            try:
                json_list_data = json.loads(json_response_string)
                
                if not isinstance(json_list_data, list):
                     raise json.JSONDecodeError("AI did not return a list.", json_response_string, 0)

                for j, json_data in enumerate(json_list_data):
                    if j >= len(batch_of_scenes_data): break 
                    
                    scene_data_from_table = batch_of_scenes_data[j]
                    scene_number = i + 1 + j
                    
                    # Dữ liệu cơ bản từ bảng Markdown
                    row_data = {
                        "Scene ID": scene_number,
                        "Table: Timecode": scene_data_from_table['timecode'],
                        "Table: Description": scene_data_from_table['description'],
                        "Table: Camera": scene_data_from_table['camera'],
                        "Table: Sound": scene_data_from_table['sound'],
                        "Table: Emotion": scene_data_from_table['emotion'],
                    }
                    
                    # Thêm toàn bộ JSON
                    row_data["JSON Prompt (Full)"] = json.dumps(json_data, indent=2)
                    
                    # Thêm các cột đã "làm phẳng" từ JSON (để tham khảo)
                    core_idea = json_data.get("1. CORE_IDEA", {})
                    row_data["JSON: Scene Purpose"] = core_idea.get("scene_purpose", "N/A")
                    chars = json_data.get("2. CHARACTERS_AND_ACTIONS", [{}])
                    if chars: 
                        row_data["JSON: Character 1"] = chars[0].get("character", "N/A")
                        # Lấy mô tả chi tiết 300-400 từ
                        row_data["JSON: Detailed Description (300-400 words)"] = chars[0].get("action_and_expression", "N/A")
                    
                    all_scenes_data.append(row_data)

            except json.JSONDecodeError as e:
                st.warning(f"   ! Error: AI did not return a valid JSON LIST for batch {batch_num}. Error: {e}")
            except Exception as e:
                st.warning(f"   ! Unknown error processing JSON list for batch {batch_num}. Error: {e}")
                
        # --- STEP 5: EXPORT TO EXCEL FILE ---
        progress_bar.progress(98, text="[5/5] Exporting data to Excel file...")
        try:
            df = pd.DataFrame(all_scenes_data)
            
            base_filename = "prehumanfile_veo3_prompts"
            file_extension = ".xlsx"
            output_filename = base_filename + file_extension
            
            # Trên Replit, chúng ta không cần vòng lặp 'while' phức tạp
            # vì không có ai đang "mở" tệp.
            try:
                df.to_excel(output_filename, index=False, engine='openpyxl')
                
                progress_bar.progress(100, text="Complete!")
                st.success(f"Successfully saved the detailed script to: {output_filename}")
                
                # Thêm nút tải về (Cách của Replit)
                with open(output_filename, "rb") as f:
                    st.download_button(
                        label="Download Excel File (Veo 3 JSONs)",
                        data=f,
                        file_name=output_filename,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                return # Thoát khỏi hàm main_automation thành công
                
            except Exception as e:
                st.error(f"😥 Error exporting to Excel: {e}") 

        except Exception as e:
            st.error(f"😥 An unexpected error occurred during data preparation for Excel: {e}")

    except Exception as e:
        st.error(f"😥 An unexpected error occurred during the automation process: {e}")
        st.exception(e) # In ra toàn bộ lỗi để debug

# --- GIAO DIỆN STREAMLIT (Đã Nâng cấp) ---

st.set_page_config(layout="wide", page_title="PrehumanFile Script Generator")
st.title("🎬 PrehumanFile - VEO 3 Script Generator")
st.info("This tool generates a full cinematic script and the corresponding Veo 3 JSON prompts from a single topic.")

# Vùng nhập liệu
with st.form(key="script_form"):
    topic_input = st.text_input("Enter the Video Topic:", 
                              placeholder="e.g., 'The First Fire' or 'Tribe vs Giant Eagle'")
    duration_input = st.number_input("Enter Video Duration (in minutes):", 
                                      min_value=1, max_value=60, value=10, step=1)
    
    submit_button = st.form_submit_button(label="Generate Full Script & JSONs")

# Xử lý khi nhấn nút
if submit_button:
    if not topic_input:
        st.error("Please enter a Video Topic.")
    elif not GOOGLE_API_KEY or "YOUR_NEW_API_KEY" in GOOGLE_API_KEY:
        st.error("Please configure your GOOGLE_API_KEY in the 'Secrets' tab (lock icon).")
    else:
        with st.spinner(f"Generating full episode for '{topic_input}'... This will take several minutes. Please wait."):
            main_automation(topic_input, duration_input)



