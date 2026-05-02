# app.py
import streamlit as st
import os
from pathlib import Path
from PIL import Image
import tempfile
import zipfile
import io
from datetime import datetime
import traceback

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

# デバッグモード
debug_mode = st.sidebar.checkbox("🔍 デバッグモード", False)

# ファイルアップロード
uploaded_files = st.file_uploader(
    "画像をアップロード（複数選択可）",
    type=['jpg', 'jpeg', 'png', 'bmp', 'gif', 'tiff'],
    accept_multiple_files=True
)

if not uploaded_files:
    st.info("👆 画像ファイルをアップロードしてください")
    st.stop()

# ========== メイン処理 ==========

st.success(f"✅ {len(uploaded_files)}枚の画像を読み込みました")

# 画像プレビュー
with st.expander("📸 アップロードされた画像を確認", expanded=False):
    cols = st.columns(4)
    for idx, file in enumerate(uploaded_files[:8]):
        with cols[idx % 4]:
            image = Image.open(file)
            st.image(image, caption=file.name, use_column_width=True)
    
    if len(uploaded_files) > 8:
        st.info(f"他 {len(uploaded_files) - 8}枚")

# 一時ディレクトリに保存
temp_dir = tempfile.mkdtemp()
file_paths = []

with st.spinner("画像を準備中..."):
    for file in uploaded_files:
        temp_path = os.path.join(temp_dir, file.name)
        with open(temp_path, "wb") as f:
            f.write(file.getbuffer())
        file_paths.append(temp_path)

# ImageRenamer初期化
try:
    renamer = ImageRenamer(file_paths)
    
    # OCR初期化（デバッグ情報表示）
    if use_ocr:
        with st.spinner("OCRエンジン初期化中..."):
            renamer.initialize_ocr()
        
        if debug_mode:
            st.success("✅ OCRエンジン初期化完了")
            
            # Tesseractバージョン確認
            try:
                import pytesseract
                version = pytesseract.get_tesseract_version()
                st.info(f"📌 Tesseract バージョン: {version}")
            except Exception as e:
                st.warning(f"⚠️ Tesseractバージョン取得失敗: {e}")
    
except Exception as e:
    st.error(f"❌ 初期化エラー: {e}")
    if debug_mode:
        st.code(traceback.format_exc())
    st.stop()

# ========== デバッグモード: OCR詳細表示 ==========

if debug_mode:
    st.markdown("---")
    st.subheader("🔍 デバッグ情報")
    
    for idx, (uploaded_file, tmp_path) in enumerate(zip(uploaded_files, file_paths)):
        with st.expander(f"📷 画像 {idx+1}: {uploaded_file.name}", expanded=(idx==0)):
            
            col1, col2 = st.columns([1, 2])
            
            with col1:
                # 画像表示
                image = Image.open(tmp_path)
                st.image(image, caption=uploaded_file.name, use_column_width=True)
            
            with col2:
                try:
                    # 通常OCR結果
                    st.markdown("##### 🔍 通常OCR結果")
                    with st.spinner("OCR実行中..."):
                        ocr_results = renamer.perform_ocr(tmp_path)
                    
                    if ocr_results:
                        st.success(f"✅ {len(ocr_results)}個のテキストを検出")
                        for i, text in enumerate(ocr_results, 1):
                            st.code(f"{i}. {text}", language=None)
                    else:
                        st.warning("⚠️ テキストが検出されませんでした")
                    
                    # 情報板OCR結果
                    st.markdown("##### 🟩 情報板OCR結果")
                    with st.spinner("情報板OCR実行中..."):
                        panel_results = renamer.perform_info_panel_ocr(tmp_path)
                    
                    if panel_results:
                        st.success(f"✅ {len(panel_results)}個のテキストを検出")
                        for i, text in enumerate(panel_results, 1):
                            st.code(f"{i}. {text}", language=None)
                    else:
                        st.warning("⚠️ 情報板からテキストが検出されませんでした")
                    
                    # ラベル情報抽出結果
                    labeled_info = renamer.extract_labeled_panel_info(panel_results)
                    if labeled_info:
                        st.markdown("##### 🏷️ 抽出されたラベル情報")
                        for label, value in labeled_info.items():
                            st.text(f"{label}: {value}")
                    
                    # 生成されるファイル名
                    st.markdown("##### 📝 生成されるファイル名")
                    file_date = renamer.get_file_date(tmp_path)
                    new_name = renamer.generate_new_name(tmp_path, file_date)
                    
                    st.code(f"元: {uploaded_file.name}\n→ {new_name}", language=None)
                    
                except Exception as e:
                    st.error(f"❌ エラー: {e}")
                    st.code(traceback.format_exc())

# ========== リネームプレビュー ==========

st.markdown("---")
st.subheader("📋 リネーム後のファイル名プレビュー")

with st.spinner("プレビュー生成中..."):
    try:
        preview_data = renamer.generate_preview()
    except Exception as e:
        st.error(f"❌ プレビュー生成エラー: {e}")
        if debug_mode:
            st.code(traceback.format_exc())
        st.stop()

# プレビュー表示
for old_path, new_name in preview_data:
    old_name = os.path.basename(old_path)
    col1, col2 = st.columns([1, 1])
    with col1:
        st.text(f"元: {old_name}")
    with col2:
        st.text(f"→ {new_name}")

# ========== ダウンロード ==========

st.markdown("---")

if st.button("🚀 リネーム実行してダウンロード", type="primary"):
    with st.spinner("リネーム処理中..."):
        try:
            # ZIPファイル作成
            zip_buffer = io.BytesIO()
            
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for old_path, new_name in preview_data:
                    # ファイルをZIPに追加
                    zip_file.write(old_path, new_name)
            
            zip_buffer.seek(0)
            
            # タイムスタンプ付きファイル名
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            zip_filename = f"renamed_images_{timestamp}.zip"
            
            # ダウンロードボタン
            st.download_button(
                label="📦 ZIPファイルをダウンロード",
                data=zip_buffer,
                file_name=zip_filename,
                mime="application/zip"
            )
            
            st.success("✅ リネーム完了！上のボタンからダウンロードしてください")
            
        except Exception as e:
            st.error(f"❌ リネーム処理エラー: {e}")
            if debug_mode:
                st.code(traceback.format_exc())

# ========== クリーンアップ ==========

# 一時ファイル削除（セッション終了時）
if st.session_state.get('cleanup_done') is None:
    import atexit
    
    def cleanup():
        try:
            import shutil
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
        except:
            pass
    
    atexit.register(cleanup)
    st.session_state['cleanup_done'] = True

# ========== フッター ==========

st.markdown("---")
st.markdown("""
### 💡 使い方

1. **画像をアップロード**: 複数枚選択可能
2. **設定を確認**: サイドバーで調整
3. **デバッグモード**: OCRの動作を詳しく確認したい場合はON
4. **プレビュー確認**: リネーム後のファイル名を確認
5. **ダウンロード**: ZIPファイルで一括ダウンロード

### 📌 対応している画像形式

- JPG/JPEG
- PNG
- BMP
- GIF
- TIFF

### 🔧 OCRについて

- **Tesseract** を使用（日本語対応）
- 緑色の工事情報板から自動でテキストを抽出
- 工事件名、工事場所、施工状況を認識

### ⚠️ 注意事項

- アップロードできるファイルサイズ: 1枚あたり最大200MB
- 処理時間は画像の枚数とサイズによって変わります
- デバッグモードをONにすると詳細な情報が表示されます
""")

st.markdown("---")
st.caption("📷 画像一括リネームツール v1.0 | Powered by Streamlit")
