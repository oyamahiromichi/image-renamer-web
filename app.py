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
import shutil
import configparser  # ← 追加

# 既存のImageRenamerクラスをインポート
from image_renamer_ocr import ImageRenamer


# ===== 新しい関数群（ここから追加） =====

def load_config_from_ini():
    """INIファイルから設定を読み込み"""
    config = {
        'IMPORTANT_KEYWORDS': [],
        'EXCLUDE_WORDS': [],
        'OCR_REPLACEMENTS': {}
    }
    
    ini_path = Path('ocr_keywords.ini')
    if not ini_path.exists():
        return config
    
    try:
        parser = configparser.ConfigParser()
        parser.read(ini_path, encoding='utf-8-sig')
        
        if parser.has_section('KEYWORDS') and parser.has_option('KEYWORDS', 'important'):
            keywords = parser.get('KEYWORDS', 'important')
            config['IMPORTANT_KEYWORDS'] = [kw.strip() for kw in keywords.split(',') if kw.strip()]
        
        if parser.has_section('EXCLUDE') and parser.has_option('EXCLUDE', 'words'):
            words = parser.get('EXCLUDE', 'words')
            config['EXCLUDE_WORDS'] = [w.strip() for w in words.split(',') if w.strip()]
        
        if parser.has_section('REPLACEMENTS'):
            for key, value in parser.items('REPLACEMENTS'):
                if key != 'default':
                    config['OCR_REPLACEMENTS'][key] = value
    
    except Exception as e:
        st.error(f"設定ファイル読み込みエラー: {e}")
    
    return config


def save_keywords_to_ini(section_type, keywords):
    """キーワードをINIファイルに保存"""
    ini_path = Path('ocr_keywords.ini')
    
    try:
        parser = configparser.ConfigParser()
        
        # 既存のINIファイルを読み込み
        if ini_path.exists():
            parser.read(ini_path, encoding='utf-8-sig')
        
        # セクションがなければ作成
        if section_type == 'IMPORTANT_KEYWORDS':
            if not parser.has_section('KEYWORDS'):
                parser.add_section('KEYWORDS')
            parser.set('KEYWORDS', 'important', ','.join(keywords))
        
        elif section_type == 'EXCLUDE_WORDS':
            if not parser.has_section('EXCLUDE'):
                parser.add_section('EXCLUDE')
            parser.set('EXCLUDE', 'words', ','.join(keywords))
        
        # ファイルに書き込み
        with open(ini_path, 'w', encoding='utf-8') as f:
            parser.write(f)
        
        return True
    
    except Exception as e:
        st.error(f"保存エラー: {e}")
        return False


def show_keyword_editor():
    """キーワード編集画面（Streamlit版）"""
    st.title("⚙️ キーワード設定")
    
    config = load_config_from_ini()
    
    tab1, tab2 = st.tabs(["📌 重要キーワード", "🚫 除外キーワード"])
    
    # ===== タブ1: 重要キーワード =====
    with tab1:
        st.subheader("📌 重要キーワード")
        st.info("画像から抽出する重要なキーワードを登録します")
        
        keywords = config.get('IMPORTANT_KEYWORDS', [])
        
        keywords_text = st.text_area(
            "キーワード（1行に1つ）",
            value="\n".join(keywords),
            height=400,
            help="1行に1つのキーワードを入力してください"
        )
        
        col1, col2 = st.columns([3, 1])
        
        with col1:
            if st.button("💾 重要キーワードを保存", type="primary", use_container_width=True):
                new_keywords = [kw.strip() for kw in keywords_text.split('\n') if kw.strip()]
                
                if save_keywords_to_ini('IMPORTANT_KEYWORDS', new_keywords):
                    st.success(f"✅ {len(new_keywords)}個のキーワードを保存しました")
                    st.rerun()
                else:
                    st.error("❌ 保存に失敗しました")
        
        with col2:
            st.metric("登録数", len(keywords))
    
    # ===== タブ2: 除外キーワード =====
    with tab2:
        st.subheader("🚫 除外キーワード")
        st.info("ファイル名に含めたくないキーワードを登録します")
        
        exclude_words = config.get('EXCLUDE_WORDS', [])
        
        exclude_text = st.text_area(
            "除外キーワード（1行に1つ）",
            value="\n".join(exclude_words),
            height=400
        )
        
        col1, col2 = st.columns([3, 1])
        
        with col1:
            if st.button("💾 除外キーワードを保存", type="primary", use_container_width=True):
                new_exclude = [kw.strip() for kw in exclude_text.split('\n') if kw.strip()]
                
                if save_keywords_to_ini('EXCLUDE_WORDS', new_exclude):
                    st.success(f"✅ {len(new_exclude)}個の除外キーワードを保存しました")
                    st.rerun()
                else:
                    st.error("❌ 保存に失敗しました")
        
        with col2:
            st.metric("登録数", len(exclude_words))


# ===== 新しい関数群（ここまで） =====


st.set_page_config(
    page_title="画像リネームツール",
    page_icon="📷",
    layout="wide"
)

st.title("📷 画像一括リネームツール")
st.markdown("**iPadでも使える Web版**")

# サイドバー設定
st.sidebar.header("⚙️ 設定")

# ===== キーワード設定ボタン（新規追加） =====
if st.sidebar.button("🔧 キーワード設定を開く", use_container_width=True):
    st.session_state.show_keyword_editor = True

st.sidebar.markdown("---")  # 区切り線

# キーワードエディタを表示
if st.session_state.get('show_keyword_editor', False):
    show_keyword_editor()
    
    # 閉じるボタン
    if st.button("← メイン画面に戻る"):
        st.session_state.show_keyword_editor = False
        st.rerun()
    
    st.stop()  # メイン処理を止める

# ===== ここから既存の設定項目 =====
prefix = st.sidebar.text_input("プレフィックス", "photo")
include_date = st.sidebar.checkbox("日付を含める", True)
use_ocr = st.sidebar.checkbox("OCR使用", True)
info_panel_position = st.sidebar.selectbox(
    "情報板位置",
    ["auto", "left", "right"],
    index=0
)

# デバッグモード
debug_mode = st.sidebar.checkbox("🔍 デバッグモード", True)

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
            file.seek(0)
            image = Image.open(file)
            st.image(image, caption=file.name, use_column_width=True)
    
    if len(uploaded_files) > 8:
        st.info(f"他 {len(uploaded_files) - 8}枚")

# 一時ディレクトリ作成
if 'temp_dir' not in st.session_state:
    st.session_state.temp_dir = tempfile.mkdtemp()

temp_dir = st.session_state.temp_dir
file_paths = []

# ファイルを一時保存
with st.spinner("画像を準備中..."):
    for file in uploaded_files:
        file.seek(0)
        temp_path = os.path.join(temp_dir, file.name)
        with open(temp_path, "wb") as f:
            f.write(file.read())
        file_paths.append(temp_path)

# ImageRenamer初期化
try:
    renamer = ImageRenamer(file_paths)
    
except Exception as e:
    st.error(f"❌ 初期化エラー: {e}")
    if debug_mode:
        st.code(traceback.format_exc())
    st.stop()

# OCR初期化
if use_ocr:
    try:
        with st.spinner("OCRエンジン初期化中..."):
            renamer.initialize_ocr()
        
        if debug_mode:
            st.success("✅ OCRエンジン初期化完了")
            
            # Tesseract確認
            try:
                import subprocess
                result = subprocess.run(['tesseract', '--version'], 
                                      capture_output=True, text=True, timeout=5)
                
                if result.returncode == 0:
                    st.info(f"📌 Tesseract インストール確認OK")
                    with st.expander("詳細を表示"):
                        st.code(result.stdout)
                else:
                    st.warning("⚠️ Tesseractコマンドが実行できません")
                    
            except FileNotFoundError:
                st.error("❌ Tesseractがインストールされていません")
                
            except subprocess.TimeoutExpired:
                st.warning("⚠️ Tesseractコマンドがタイムアウトしました")
                
            except Exception as e:
                st.warning(f"⚠️ Tesseract確認エラー: {e}")
    
    except Exception as e:
        st.error(f"❌ OCR初期化エラー: {e}")
        if debug_mode:
            st.code(traceback.format_exc())
        st.stop()

# ========== デバッグモード: OCR詳細表示 ==========

if debug_mode:
    st.markdown("---")
    st.subheader("🔍 デバッグ情報")
    
    for idx in range(min(1, len(file_paths))):
        tmp_path = file_paths[idx]
        uploaded_file = uploaded_files[idx]
        
        with st.expander(f"📷 画像 {idx+1}: {uploaded_file.name}", expanded=True):
            
            col1, col2 = st.columns([1, 2])
            
            with col1:
                image = Image.open(tmp_path)
                st.image(image, caption=uploaded_file.name, use_column_width=True)
            
            with col2:
                try:
                    st.markdown("##### 🔍 通常OCR結果")
                    with st.spinner("OCR実行中..."):
                        ocr_results = renamer.perform_ocr(tmp_path)
                    
                    if ocr_results:
                        st.success(f"✅ {len(ocr_results)}個のテキストを検出")
                        for i, text in enumerate(ocr_results, 1):
                            st.code(f"{i}. {text}", language=None)
                    else:
                        st.warning("⚠️ テキストが検出されませんでした")
                    
                    st.markdown("##### 🟩 情報板OCR結果")
                    with st.spinner("情報板OCR実行中..."):
                        panel_results = renamer.perform_info_panel_ocr(tmp_path)
                    
                    if panel_results:
                        st.success(f"✅ {len(panel_results)}個のテキストを検出")
                        for i, text in enumerate(panel_results, 1):
                            st.code(f"{i}. {text}", language=None)
                    else:
                        st.warning("⚠️ 情報板からテキストが検出されませんでした")
                    
                    if panel_results:
                        labeled_info = renamer.extract_labeled_panel_info(panel_results)
                        if labeled_info:
                            st.markdown("##### 🏷️ 抽出されたラベル情報")
                            for label, value in labeled_info.items():
                                st.text(f"{label}: {value}")
                    
                    st.markdown("##### 📝 生成されるファイル名")
                    file_date = renamer.get_file_date(tmp_path)
                    new_name = renamer.generate_new_name(tmp_path, file_date)
                    st.code(f"元: {uploaded_file.name}\n→ {new_name}", language=None)
                    
                except Exception as e:
                    st.error(f"❌ エラー: {e}")
                    st.code(traceback.format_exc())
    
    if len(file_paths) > 1:
        st.info(f"💡 デバッグモードでは最初の1枚のみ詳細表示しています（残り{len(file_paths)-1}枚）")

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
        st.text(f"📄 {old_name}")
    with col2:
        st.text(f"→ {new_name}")

# ========== ダウンロード ==========

st.markdown("---")

if st.button("🚀 リネーム実行してダウンロード", type="primary", use_container_width=True):
    with st.spinner("リネーム処理中..."):
        try:
            zip_buffer = io.BytesIO()
            
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for old_path, new_name in preview_data:
                    zip_file.write(old_path, new_name)
            
            zip_buffer.seek(0)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            zip_filename = f"renamed_images_{timestamp}.zip"
            
            st.download_button(
                label="📦 ZIPファイルをダウンロード",
                data=zip_buffer,
                file_name=zip_filename,
                mime="application/zip",
                use_container_width=True
            )
            
            st.success("✅ リネーム完了！上のボタンからダウンロードしてください")
            
        except Exception as e:
            st.error(f"❌ リネーム処理エラー: {e}")
            if debug_mode:
                st.code(traceback.format_exc())

# ========== クリーンアップ ==========

def cleanup_temp_files():
    if 'temp_dir' in st.session_state:
        temp_dir = st.session_state.temp_dir
        try:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                del st.session_state.temp_dir
        except Exception:
            pass

if 'cleanup_registered' not in st.session_state:
    import atexit
    atexit.register(cleanup_temp_files)
    st.session_state.cleanup_registered = True

# ========== フッター ==========

st.markdown("---")

with st.expander("💡 使い方・ヘルプ"):
    st.markdown("""
### 📖 使い方

1. **画像をアップロード**: 「Browse files」をクリックして複数枚選択
2. **設定を確認**: 左サイドバーで設定を調整
3. **デバッグモード**: OCRの詳細を確認したい場合はON
4. **プレビュー確認**: リネーム後のファイル名を確認
5. **ダウンロード**: 「リネーム実行してダウンロード」ボタンをクリック

---

### 📌 対応している画像形式

- **JPG/JPEG** - 最も一般的な形式
- **PNG** - 透過対応
- **BMP** - Windows標準形式
- **GIF** - アニメーション対応
- **TIFF** - 高品質画像

---

### 🔧 OCRについて

- **Tesseract OCR** を使用（日本語対応）
- 緑色の工事情報板から自動でテキストを抽出
- 以下の情報を認識します：
  - 工事件名
  - 工事場所
  - 施工状況（施工前/施工中/施工後）

---

### ⚙️ 設定項目

- **プレフィックス**: ファイル名の先頭に付ける文字列
- **日付を含める**: EXIF情報から撮影日を取得してファイル名に含める
- **OCR使用**: 画像内のテキストを認識してファイル名に反映
- **情報板位置**: 
  - `auto`: 自動判定（推奨）
  - `left`: 左側固定
  - `right`: 右側固定

---

### ⚠️ 注意事項

- **ファイルサイズ**: 1枚あたり最大200MB
- **処理時間**: 画像の枚数とサイズによって変わります
- **デバッグモード**: 詳細情報を確認できますが、処理が遅くなります
- **一時ファイル**: アップロードされたファイルは処理後に自動削除されます

---

### 🐛 トラブルシューティング

**Q: OCRが文字を認識しない**
- デバッグモードをONにして、OCR結果を確認してください
- 画像が小さすぎたり、文字がぼやけている場合は認識できません
- 情報板の位置設定を変更してみてください

**Q: ファイル名が正しくない**
- プレビューで確認してから実行してください
- 設定を調整して再度試してください

**Q: ダウンロードできない**
- ブラウザのポップアップブロックを解除してください
- ファイルサイズが大きすぎる場合は枚数を減らしてください

**Q: エラーが出る**
- デバッグモードをONにしてエラー内容を確認してください
- 画像ファイルが破損していないか確認してください

---

### 📧 お問い合わせ

問題が解決しない場合は、デバッグモードのエラー内容をスクリーンショットしてお問い合わせください。
    """)

st.markdown("---")
st.caption("📷 画像一括リネームツール v1.0 | Powered by Streamlit + Tesseract OCR")
