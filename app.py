import streamlit as st
import os
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
from google import genai
from dotenv import load_dotenv

# โหลดตัวแปรจากไฟล์ .env
load_dotenv(override=True)

# ==========================================
# 1. ตั้งค่าหน้าเว็บ
# ==========================================
st.set_page_config(page_title="MilkLab AI", page_icon="🥛")
st.title("🥛 MilkLab AI Assistant")

# ==========================================
# 2. ระบบ RAG: ฟังก์ชันโหลดข้อมูลและสร้าง Index
# (ใช้ @st.cache_resource เพื่อให้โหลดแค่ครั้งเดียว ไม่โหลดใหม่ทุกครั้งที่พิมพ์)
# ==========================================


@st.cache_resource
def load_rag_system():
    # 2.1 โหลด menu_kb.md แล้ว split เป็น chunk (หั่นตามย่อหน้า)
    with open("menu_kb.md", "r", encoding="utf-8") as f:
        text = f.read()
    chunks = [c.strip() for c in text.split('\n\n') if c.strip()]

    # 2.2 encode chunk ด้วย sentence-transformers
    model = SentenceTransformer(
        'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
    embeddings = model.encode(chunks)

    # 2.3 สร้าง faiss index เพื่อเอาไว้ค้นหา
    dimension = embeddings.shape[1]
    index = faiss.IndexFlatL2(dimension)
    index.add(np.array(embeddings))

    return chunks, model, index


# เรียกใช้งานระบบ RAG
chunks, embedder, index = load_rag_system()

# ==========================================
# 3. เตรียมเชื่อมต่อ AI (Gemini)
# ==========================================
api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
if not api_key:
    st.error(
        "⚠️ ไม่พบ API Key กรุณาตรวจสอบว่ามีตัวแปร GOOGLE_API_KEY ในไฟล์ .env หรือยัง")
    st.stop()

client = genai.Client(api_key=api_key)

# ==========================================
# 4. สร้าง chat UI ด้วย Streamlit
# ==========================================
# เช็กว่ามีประวัติแชทหรือยัง ถ้ายังให้สร้างลิสต์ว่างๆ
if "messages" not in st.session_state:
    st.session_state.messages = []

# แสดงประวัติแชทบนหน้าจอ
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# ==========================================
# 5. รับคำถามและค้นหาคำตอบ (Retrieve & Generate)
# ==========================================
if prompt := st.chat_input("ถามอะไรเกี่ยวกับร้าน MilkLab ได้เลยครับ..."):
    # 5.1 แสดงคำถามของลูกค้าบนจอ
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    # 5.2 Retrieve: ค้นหา Top-K chunks ที่ตรงกับคำถามที่สุด (เอามา 3 อันดับแรก)
    question_embedding = embedder.encode([prompt])
    k = 3
    distances, indices = index.search(np.array(question_embedding), k)

    # เอาข้อความที่ค้นเจอมาเรียงต่อกันเพื่อเตรียมส่งให้ AI
    retrieved_context = "\n\n".join([chunks[i]
                                    for i in indices[0] if i < len(chunks)])

    # 5.3 Generate: ใส่ context ลงใน Gemini prompt
    system_prompt = f"""
    คุณคือพนักงานร้าน MilkLab คอยตอบคำถามลูกค้าด้วยความสุภาพและเป็นกันเอง
    กรุณาใช้ "ข้อมูลอ้างอิง" ด้านล่างนี้ในการตอบคำถามเท่านั้น
    หากลูกค้าถามนอกเหนือจากข้อมูลนี้ ให้ตอบว่า "ขออภัยครับ ทางร้านยังไม่มีข้อมูลในส่วนนี้"
    
    ข้อมูลอ้างอิง:
    {retrieved_context}
    """

    with st.chat_message("assistant"):
        try:
            # ใช้รุ่น 2.0-flash ที่เราเทสต์กันว่าเสถียรที่สุด
            response = client.models.generate_content(
                model='gemini-3.5-flash',
                contents=[system_prompt, prompt],
            )
            st.markdown(response.text)
            st.session_state.messages.append(
                {"role": "assistant", "content": response.text})
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาดในการเชื่อมต่อ AI: {e}")
