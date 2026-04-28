# app.py
import streamlit as st
import os
from pathlib import Path
from PIL import Image
import tempfile
import zipfile
import io

# 既存のImageRenamerクラスをインポート
from image_renamer_ocr import ImageRenamer

st.set_page_config(
    page_title="画像リネームツール",
    page_icon="📷",
    layout="wide"
)

st.title("📷 画像一括リネームツール")
st.markdown("**iPadでも使える Web版**")

# サイドバー設定
st.sidebar.header("⚙️ 設定")
prefix = st.sidebar.text_input("プレフィックス", "photo")
include_date = st.sidebar.checkbox("日付を含める", True)
use_ocr = st.sidebar.checkbox("OCR使用", True)
info_panel_position = st.sidebar.selectbox(
    "情報板位置",
    ["auto", "left", "right"],
    index=0
)

# ファイルアップロード
uploaded_files = st.file_uploader(
    "画像をアップロード（複数選択可）",
    type=['jpg', 'jpeg', 'png'],
    accept_multiple_files=True
)

if uploaded_files:
    st.success(f"✅ {len(uploaded_files)}枚の画像を読み込みました")
    
    # プレビュー表示
    cols = st.columns(4)
    for idx, file in enumerate(uploaded_files[:8]):
        with cols[idx % 4]:
            image = Image.open(file)
            st.image(image, caption=file.name, use_column_width=True)
    
    if len(uploaded_files) > 8:
        st.info(f"他 {len(uploaded_files) - 8}枚")
    
    # 処理実行ボタン
    if st.button("🚀 リネーム処理を実行", type="primary"):
        with st.spinner("処理中..."):
            # 一時ディレクトリに保存
            temp_dir = tempfile.mkdtemp()
            file_paths = []
            
            for file in uploaded_files:
                temp_path = os.path.join(temp_dir, file.name)
                with open(temp_path, "wb") as f:
                    f.write(file.getbuffer())
                file_paths.append(temp_path)
            
            # リネーム処理
            renamer = ImageRenamer(file_paths)
            renamer.initialize_ocr()
            preview_data = renamer.generate_preview()
            
            # 結果表示
            st.subheader("📋 リネーム結果")
            for old_path, new_name in preview_data:
                col1, col2 = st.columns([1, 1])
                with col1:
                    st.text(f"元: {os.path.basename(old_path)}")
                with col2:
                    st.text(f"→ {new_name}")
            
            # ZIPダウンロード
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w") as zip_file:
                for old_path, new_name in preview_data:
                    zip_file.write(old_path, new_name)
            
            zip_buffer.seek(0)
            
            st.download_button(
                label="📦 リネーム済み画像をダウンロード",
                data=zip_buffer,
                file_name="renamed_images.zip",
                mime="application/zip"
            )

else:
    st.info("👆 画像ファイルをアップロードしてください")