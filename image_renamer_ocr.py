# -*- coding: utf-8 -*-
"""
画像一括リネームツール(EasyOCR + Tesseract 複合版)
機能: 複数OCR、キーワード抽出、日付順ソート、連番付与
"""

import sys
import io
import configparser

# 🔧 修正: Streamlit環境用にログ出力を無効化
class DummyWriter:
    def write(self, text):
        pass
    def flush(self):
        pass

sys.stdout = DummyWriter()
sys.stderr = DummyWriter()

import os
import re
from datetime import datetime
from pathlib import Path
from PIL import Image
from PIL.ExifTags import TAGS
import cv2
import numpy as np
import pytesseract

# 🔧 Streamlit Cloud用：Tesseractは自動検出されるためパス設定不要
# ローカルWindows環境で実行する場合のみ以下のコメントを外してください
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# === 設定 ===
PREFIX = "photo"
INCLUDE_DATE = True
CLASSIFY_BY_NAME = True
USE_EXIF_DATE = True
START_NUMBER = 1
DIGIT_COUNT = 3
SORT_BY_DATE = True
USE_OCR = True

# OCR設定
ADD_OCR_TEXT = True
USE_FULL_OCR_TEXT = True
MAX_FILENAME_LENGTH = 200
OCR_CONFIDENCE_THRESHOLD = 0.5
KEEP_CONFIDENCE_THRESHOLD = 0.8

# OCRモデルディレクトリ（スクリプトと同じフォルダー内の models フォルダー）
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OCR_MODEL_DIR = os.path.join(SCRIPT_DIR, 'models')

# OCRエンジン設定
USE_EASYOCR = True
USE_TESSERACT = True
TESSERACT_PRIORITY = 0.9  # Tesseract結果の信頼度補正係数

# 高速化設定
OCR_LANGUAGES = ['ja']
MAX_OCR_IMAGE_SIZE = 1800
INFO_PANEL_UPSCALE = 2.0
FAST_MODE = True

# 情報板OCR設定
USE_INFO_PANEL_OCR = True

# 情報板の位置設定 ("left", "right", "auto")
INFO_PANEL_POSITION = "auto"  # "left"=左側固定, "right"=右側固定, "auto"=自動判定

# 左側情報板のクロップ座標 (x1, y1, x2, y2) ※比率
INFO_PANEL_CROP_LEFT = (0.00, 0.54, 0.42, 1.00)

# 右側情報板のクロップ座標 (x1, y1, x2, y2) ※比率  
INFO_PANEL_CROP_RIGHT = (0.58, 0.54, 1.00, 1.00)

INFO_PANEL_LABELS = [
    "工事件名",
    "工事場所",
    "施工状況",
]

SHORT_NAME_LABELS = {
    "工事件名": "",
    "工事場所": "",
    "施工状況": "",
}

# 除外文字設定
EXCLUDE_CHARS = ['|', '/', '\\', ':', '*', '?', '"', '<', '>']
EXCLUDE_CHAR_REPLACEMENT = ''

# グローバル変数
IMPORTANT_KEYWORDS = []
EXCLUDE_WORDS = []
OCR_REPLACEMENTS = {}
EXCLUDE_PATTERNS = []

DEFAULT_EXCLUDE_PATTERNS = [
    r'^[zZ]\d+$',
    r'^\d{1,2}$',
    r'^[!@#$%^&*()_+=\-\[\]{}|\\:;"\'<>,.?/~`]+$',
    r'^\d{4}[年/\-\.]\d{1,2}[月/\-\.]\d{1,2}',
    r'^令和\d+年',
    r'^平成\d+年',
    r'^\d+:\d+',
    r'^第\d+号$',
    r'^様式第?\d+号?$',
    r'^[（(]\d+[)）]$',
    r'^[一二三四五六七八九十]+$',
    r'^記入例$',
    r'^記入欄$',
    r'^添付書類$',
]


def load_config_from_ini(ini_path=None):
    """INIファイルから設定を読み込む"""
    if ini_path is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        ini_path = os.path.join(script_dir, 'ocr_keywords.ini')
    
    config = {
        'IMPORTANT_KEYWORDS': [],
        'EXCLUDE_WORDS': [],
        'OCR_REPLACEMENTS': {},
        'EXCLUDE_PATTERNS': []
    }
    
    if not os.path.exists(ini_path):
        print(f"⚠️  設定ファイルが見つかりません: {ini_path}")
        return config
    
    try:
        parser = configparser.ConfigParser()
        parser.read(ini_path, encoding='utf-8-sig')
        
        if parser.has_section('KEYWORDS'):
            if parser.has_option('KEYWORDS', 'important'):
                important = parser.get('KEYWORDS', 'important')
                config['IMPORTANT_KEYWORDS'] = [
                    kw.strip() for kw in important.split(',') if kw.strip()
                ]
        
        if parser.has_section('EXCLUDE'):
            if parser.has_option('EXCLUDE', 'words'):
                words = parser.get('EXCLUDE', 'words')
                config['EXCLUDE_WORDS'] = [
                    w.strip() for w in words.split(',') if w.strip()
                ]
        
        if parser.has_section('REPLACEMENTS'):
            for key, value in parser.items('REPLACEMENTS'):
                if key != 'default':
                    config['OCR_REPLACEMENTS'][key] = value
        
        if parser.has_section('PATTERNS'):
            if parser.has_option('PATTERNS', 'exclude'):
                patterns = parser.get('PATTERNS', 'exclude')
                config['EXCLUDE_PATTERNS'] = [
                    p.strip() for p in patterns.split(',') if p.strip()
                ]
        
        print(f"✅ 設定ファイル読み込み成功: {ini_path}")
        print(f"   重要キーワード: {len(config['IMPORTANT_KEYWORDS'])}個")
        print(f"   除外単語: {len(config['EXCLUDE_WORDS'])}個")
        print(f"   置換ルール: {len(config['OCR_REPLACEMENTS'])}個")
        print(f"   除外パターン: {len(config['EXCLUDE_PATTERNS'])}個")
        
    except Exception as e:
        print(f"⚠️  設定ファイル読み込みエラー: {e}")
    
    return config


class ImageRenamer:
    """画像リネーム処理クラス（EasyOCR + Tesseract 複合版）"""
    
    def __init__(self, files):
       self.files = files
       self.easyocr_reader = None
    
       # OCR結果キャッシュ
       self.ocr_cache = {}
       self.panel_ocr_cache = {}
    
       # 情報板位置を自動判定
       self.info_panel_position = INFO_PANEL_POSITION
       if self.info_panel_position == "auto" and files and USE_INFO_PANEL_OCR:
           self.info_panel_position = self.detect_info_panel_position(files[0])
    
       self.config = load_config_from_ini()
       self.apply_config()
    
    def apply_config(self):
        """設定をグローバル変数に適用"""
        global IMPORTANT_KEYWORDS, EXCLUDE_WORDS, OCR_REPLACEMENTS, EXCLUDE_PATTERNS
        
        if self.config['IMPORTANT_KEYWORDS']:
            IMPORTANT_KEYWORDS = self.config['IMPORTANT_KEYWORDS']
        
        if self.config['EXCLUDE_WORDS']:
            EXCLUDE_WORDS = self.config['EXCLUDE_WORDS']
        
        if self.config['OCR_REPLACEMENTS']:
            OCR_REPLACEMENTS = self.config['OCR_REPLACEMENTS']
        
        if self.config['EXCLUDE_PATTERNS']:
            EXCLUDE_PATTERNS = self.config['EXCLUDE_PATTERNS']
        else:
            EXCLUDE_PATTERNS = DEFAULT_EXCLUDE_PATTERNS
            
    def detect_info_panel_position(self, image_path):
        """情報板が左右どちらにあるか自動判定"""
        try:
            with Image.open(Path(image_path)) as img:
                rgb = np.array(img.convert('RGB'))
                bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            
            h, w = bgr.shape[:2]
            
            # 左下と右下の緑色成分を比較
            left_roi = bgr[int(h*0.7):h, 0:int(w*0.3)]
            right_roi = bgr[int(h*0.7):h, int(w*0.7):w]
            
            # 緑色の平均値を計算
            left_green = np.mean(left_roi[:, :, 1])
            right_green = np.mean(right_roi[:, :, 1])
            
            # 🔧 修正: 判定ロジックを改善
            # HSV色空間で緑色の割合も考慮
            hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
            left_hsv = hsv[int(h*0.7):h, 0:int(w*0.3)]
            right_hsv = hsv[int(h*0.7):h, int(w*0.7):w]
            
            # 緑色範囲 (HSVで判定)
            green_lower = np.array([35, 40, 40])
            green_upper = np.array([85, 255, 255])
            
            left_green_mask = cv2.inRange(left_hsv, green_lower, green_upper)
            right_green_mask = cv2.inRange(right_hsv, green_lower, green_upper)
            
            left_green_pixels = np.sum(left_green_mask > 0)
            right_green_pixels = np.sum(right_green_mask > 0)
            
            print(f"   🔍 情報板位置判定:")
            print(f"      左側: 緑色平均={left_green:.1f}, 緑ピクセル数={left_green_pixels}")
            print(f"      右側: 緑色平均={right_green:.1f}, 緑ピクセル数={right_green_pixels}")
            
            # 緑色ピクセル数で判定 (より確実)
            if right_green_pixels > left_green_pixels * 1.1:
                print(f"   ✅ 判定結果: 右側情報板")
                return "right"
            else:
                print(f"   ✅ 判定結果: 左側情報板")
                return "left"
                
        except Exception as e:
            print(f"   ⚠️ 情報板位置判定エラー: {e}")
            return "left"  # デフォルト           
    
    def initialize_ocr(self):
        """OCRリーダーを初期化（一度だけ）"""
        # EasyOCRは使用しない
        pass

            #print("✅ EasyOCR初期化完了")
        
        if USE_TESSERACT:
            try:
                version = pytesseract.get_tesseract_version()
                print(f"✅ Tesseract検出: v{version}")
            except Exception as e:
                print(f"⚠️  Tesseract初期化エラー: {e}")
    
    def resize_for_ocr(self, img_bgr, max_size=MAX_OCR_IMAGE_SIZE):
        """OCR前に画像を縮小して高速化"""
        h, w = img_bgr.shape[:2]
        longest = max(h, w)

        if longest <= max_size:
            return img_bgr

        scale = max_size / longest
        new_w = max(1, int(w * scale))
        new_h = max(1, int(h * scale))
        
        return cv2.resize(img_bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)
    
    def get_exif_date(self, image_path):
        """EXIF情報から撮影日時を取得"""
        try:
            image = Image.open(image_path)
            exifdata = image.getexif()
            
            if exifdata:
                for tag_id, value in exifdata.items():
                    tag = TAGS.get(tag_id, tag_id)
                    
                    if tag == "DateTimeOriginal" or tag == "DateTime":
                        try:
                            return datetime.strptime(value, '%Y:%m:%d %H:%M:%S')
                        except:
                            pass
        except Exception as e:
            pass
        
        return None
    
    def get_file_date(self, filepath):
        """ファイルの日付を取得（EXIF優先、なければ更新日時）"""
        if USE_EXIF_DATE:
            exif_date = self.get_exif_date(filepath)
            if exif_date:
                return exif_date
        
        mtime = os.path.getmtime(filepath)
        return datetime.fromtimestamp(mtime)
    
    def preprocess_image(self, image_path):
        """画像前処理強化版（複数パターンでOCR精度向上）"""
        try:
            # 日本語パス対応
            with Image.open(Path(image_path)) as img:
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                img_array = np.array(img)
                img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
            
            # 高速化: 縮小
            img_bgr = self.resize_for_ocr(img_bgr)
            
            # 複数の前処理パターンを生成
            processed_images = []
            
            # グレースケール変換（共通処理）
            gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
            
            # === 処理1: 標準処理（従来の方法） ===
            denoised = cv2.fastNlMeansDenoising(gray)
            _, binary1 = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            processed_images.append(("標準", binary1))
            
            # === 処理2: コントラスト強調 ===
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
            enhanced = clahe.apply(gray)
            _, binary2 = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            processed_images.append(("コントラスト強調", binary2))
            
            # === 処理3: シャープネス強化 ===
            kernel = np.array([[-1,-1,-1], 
                             [-1, 9,-1], 
                             [-1,-1,-1]])
            sharpened = cv2.filter2D(gray, -1, kernel)
            _, binary3 = cv2.threshold(sharpened, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            processed_images.append(("シャープネス強化", binary3))
            
            # 全パターンを返す
            return processed_images
            
        except Exception as e:
            print(f"⚠️  画像前処理エラー: {e}")
            return None

    def preprocess_info_panel(self, image_path):
        """情報板を切り出してOCRしやすくする(左右対応版)"""
        try:
            with Image.open(Path(image_path)) as img:
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                rgb = np.array(img)
                bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

            # 全体を軽く縮小してから情報板切り出し
            bgr = self.resize_for_ocr(bgr)

            h, w = bgr.shape[:2]
            
            # 位置に応じてクロップ座標を選択
            if self.info_panel_position == "right":
                crop_coords = INFO_PANEL_CROP_RIGHT
                print(f"   📍 右側情報板を処理")
            else:
                crop_coords = INFO_PANEL_CROP_LEFT
                print(f"   📍 左側情報板を処理")
            
            x1 = int(w * crop_coords[0])
            y1 = int(h * crop_coords[1])
            x2 = int(w * crop_coords[2])
            y2 = int(h * crop_coords[3])

            roi = bgr[y1:y2, x1:x2]

            # デバッグ用: クロップ領域を保存（必要に応じてコメント解除）
            # debug_path = os.path.join(os.path.dirname(image_path), "debug_info_panel.jpg")
            # cv2.imwrite(debug_path, roi)
            # print(f"   💾 デバッグ画像保存: {debug_path}")

            # 拡大
            roi = cv2.resize(
                roi, None,
                fx=INFO_PANEL_UPSCALE,
                fy=INFO_PANEL_UPSCALE,
                interpolation=cv2.INTER_CUBIC
            )

            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

            bin1 = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY, 31, 15
            )

            inv1 = 255 - bin1

            return [
                ("情報板_gray", gray),
                ("情報板_inv1", inv1),
            ]

        except Exception as e:
            print(f"⚠️ 情報板前処理エラー: {e}")
            return []

    def perform_tesseract_ocr(self, processed_image):
        """Tesseract OCRを実行（信頼度付き）"""
        try:
            # 🔧 修正: 日本語OCR用の最適設定
            # --psm 6: Uniform text block（均一なテキストブロック）
            # --oem 3: LSTM neural netベース（最新）
            # -c preserve_interword_spaces=1: 単語間スペース保持
        
            custom_config = r'--psm 6 --oem 3 -c preserve_interword_spaces=1'            
            
            # 詳細データを取得（信頼度含む）
            data = pytesseract.image_to_data(
                processed_image,
                lang='jpn',
                output_type=pytesseract.Output.DICT,
                config='--psm 6'  # Uniform text block
            )
            
            results = []
            n_boxes = len(data['text'])
            
            for i in range(n_boxes):
                text = data['text'][i].strip()
                conf = float(data['conf'][i])
                
                if text and conf > 0:
                    # Tesseractの信頼度は-1～100なので正規化
                    normalized_conf = max(0.0, min(1.0, conf / 100.0))
                    # 補正係数を適用
                    adjusted_conf = normalized_conf * TESSERACT_PRIORITY
                    results.append((text, adjusted_conf))
            
            return results
            
        except Exception as e:
            print(f"      ⚠️ Tesseract OCRエラー: {e}")
            return []

    def perform_easyocr_ocr(self, processed_image):
        """EasyOCR OCRを実行"""
        try:
            result = self.easyocr_reader.readtext(
                processed_image,
                detail=1,
                paragraph=False,
                decoder='greedy'
            )
            
            results = []
            for (bbox, text, confidence) in result:
                results.append((text.strip(), confidence))
            
            return results
            
        except Exception as e:
            print(f"      ⚠️ EasyOCR OCRエラー: {e}")
            return []

    def merge_ocr_results(self, easyocr_results, tesseract_results):
        """複数OCRエンジンの結果を統合（信頼度ベース）"""
        # 結果を統合（同一文字列は信頼度の高い方を採用）
        merged = {}  # {cleaned_text: (confidence, source)}
        
        # EasyOCR結果を追加
        for text, conf in easyocr_results:
            cleaned = self.clean_ocr_text(text.strip())
            cleaned = re.sub(r'\s+', ' ', cleaned).strip()
            
            if len(cleaned) <= 1:
                continue
            
            if cleaned not in merged or conf > merged[cleaned][0]:
                merged[cleaned] = (conf, 'EasyOCR')
        
        # Tesseract結果を追加
        for text, conf in tesseract_results:
            cleaned = self.clean_ocr_text(text.strip())
            cleaned = re.sub(r'\s+', ' ', cleaned).strip()
            
            if len(cleaned) <= 1:
                continue
            
            if cleaned not in merged or conf > merged[cleaned][0]:
                merged[cleaned] = (conf, 'Tesseract')
        
        return merged

    def perform_info_panel_ocr(self, image_path):
        """左下の情報板専用OCR（Tesseractのみ）"""
        if not USE_INFO_PANEL_OCR:
            return []

        processed_images = self.preprocess_info_panel(image_path)
        if not processed_images:
            return []

        print(f"   🟩 情報板OCR開始（Tesseractのみ）")

        panel_results = []

        for method_name, processed in processed_images:
            try:
                # Tesseract実行のみ
                if USE_TESSERACT:
                    try:
                        tess_result = pytesseract.image_to_string(
                            processed,
                            lang='jpn',
                            config='--psm 6'
                        )
                        # 行ごとに分割
                        lines = [line.strip() for line in tess_result.split('\n') if line.strip()]
                        print(f"      📌 {method_name} (Tesseract): {lines}")
                        
                        # 結果を統合
                        for text in lines:
                            cleaned = self.clean_ocr_text(text)
                            cleaned = re.sub(r'\s+', ' ', cleaned).strip()

                            if len(cleaned) <= 1:
                                continue

                            # 完全一致の重複だけ除外
                            if cleaned not in panel_results:
                                panel_results.append(cleaned)
                                
                    except Exception as e:
                        print(f"      ⚠️ Tesseract情報板エラー({method_name}): {e}")
                else:
                    print(f"      ⚠️ Tesseractが無効化されています")

            except Exception as e:
                print(f"      ⚠️ 情報板OCRエラー({method_name}): {e}")

        print(f"   🟩 情報板OCR生結果: {panel_results}")
        return panel_results

    def perform_ocr(self, image_path):
        """OCR実行（Tesseract専用版・前処理強化）
        
        優先順位:
        1. 施工前 / 施工中 / 施工後
        2. 重要キーワード（全文ではなくキーワードだけ残す）
        3. 高信頼度全文（信頼度0.70以上）
        
        追加ルール:
        - 1文字以下は除外
        - 工事場所 / 施工状況 / 工事件名 は残さない
        """

        HIGH_CONFIDENCE_THRESHOLD = 0.70
        STATUS_WORDS = ["施工前", "施工中", "施工後"]
        IGNORE_LABELS = ["工事場所", "施工状況", "工事件名"]

        if not USE_OCR:
            return []

        # キャッシュ
        if image_path in self.ocr_cache:
            return self.ocr_cache[image_path]

        def strip_labels(text):
            """不要ラベルを除去"""
            cleaned = self.clean_ocr_text(text)
            for label in IGNORE_LABELS:
                cleaned = cleaned.replace(label, '')
            cleaned = re.sub(r'\s+', '', cleaned).strip()
            return cleaned

        def extract_statuses(text):
            """施工前/中/後を抽出"""
            found = []
            for status in STATUS_WORDS:
                if status in text and status not in found:
                    found.append(status)
            return found

        def extract_keywords(text):
            """重要キーワードを抽出（全文ではなくキーワードだけ返す）"""
            found = []
            normalized = re.sub(r'\s+', '', self.clean_ocr_text(text))
            
            # 設定ファイルから重要キーワードを取得
            important_keywords = self.config.get('IMPORTANT_KEYWORDS', [])
            if not important_keywords:
                important_keywords = IMPORTANT_KEYWORDS  # フォールバック
            
            for kw in important_keywords:
                kw_norm = re.sub(r'\s+', '', self.clean_ocr_text(kw))
                if kw_norm and kw_norm in normalized and kw not in found:
                    found.append(kw)
                    print(f"[重要キーワード検出] {kw} (信頼度に関係なく抽出)")
            
            return found

        def dedupe_preserve_priority(texts):
            """優先順位を壊さずに重複・包含を整理"""
            result = []
            for text in texts:
                if not text:
                    continue
                skip = False
                for adopted in result:
                    if text == adopted:
                        skip = True
                        break
                    if text in adopted or adopted in text:
                        skip = True
                        break
                    similarity = self.calculate_similarity(text, adopted)
                    if similarity >= 0.85:
                        skip = True
                        break
                if not skip:
                    result.append(text)
            return result

        try:
            # 画像読み込み
            image = cv2.imread(image_path)
            if image is None:
                print(f"⚠️  画像読み込み失敗: {image_path}")
                return []

            h, w = image.shape[:2]
            print(f"\n🔍 OCR解析: {os.path.basename(image_path)}")
            print(f"   画像サイズ: {w}x{h}")

            # 前処理パターン（複数試行）
            processed_patterns = []

            # パターン1: 標準処理
            gray1 = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            denoised1 = cv2.fastNlMeansDenoising(gray1, None, h=10, templateWindowSize=7, searchWindowSize=21)
            _, binary1 = cv2.threshold(denoised1, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            processed_patterns.append(("標準処理", binary1))

            # パターン2: コントラスト強調
            gray2 = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
            enhanced2 = clahe.apply(gray2)
            _, binary2 = cv2.threshold(enhanced2, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            processed_patterns.append(("コントラスト強化", binary2))

            # パターン3: 適応的二値化
            gray3 = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            adaptive3 = cv2.adaptiveThreshold(gray3, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
            processed_patterns.append(("適応的二値化", adaptive3))

            # パターン4: シャープネス強化
            gray4 = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            kernel = np.array([[-1,-1,-1], [-1, 9,-1], [-1,-1,-1]])
            sharpened4 = cv2.filter2D(gray4, -1, kernel)
            _, binary4 = cv2.threshold(sharpened4, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            processed_patterns.append(("シャープネス強化", binary4))

            print(f"   前処理パターン: {len(processed_patterns)}種類")

            # OCR結果を統合
            all_results = {}
            found_status_early = False
            found_keyword_early = False

            for method_name, processed in processed_patterns:
                try:
                    # リサイズ（認識率向上）
                    scale = 2.0
                    ph, pw = processed.shape
                    resized = cv2.resize(processed, (int(pw*scale), int(ph*scale)), interpolation=cv2.INTER_CUBIC)

                    # Tesseract設定（日本語＋英語）
                    custom_config = r'--oem 3 --psm 6 -l jpn+eng'

                    # OCR実行（詳細データ取得）
                    data = pytesseract.image_to_data(resized, config=custom_config, output_type=pytesseract.Output.DICT)

                    # 結果を解析
                    n_boxes = len(data['text'])
                    detected_count = 0

                    for i in range(n_boxes):
                        text = data['text'][i].strip()
                        conf = float(data['conf'][i])

                        if not text or conf <= 0:
                            continue

                        detected_count += 1

                                                # 信頼度を正規化（0.0～1.0）
                        normalized_conf = max(0.0, min(1.0, conf / 100.0))
                        adjusted_conf = normalized_conf * TESSERACT_PRIORITY

                        cleaned = self.clean_ocr_text(text.strip())
                        cleaned = re.sub(r'\s+', ' ', cleaned).strip()

                        # 1文字以下は除外
                        if len(cleaned) <= 1:
                            continue

                        # 既存結果より信頼度が高い場合のみ更新
                        if cleaned not in all_results or adjusted_conf > all_results[cleaned][0]:
                            all_results[cleaned] = (adjusted_conf, method_name)

                        # 早期終了判定用
                        if any(status in cleaned for status in STATUS_WORDS):
                            found_status_early = True

                        if any(kw in cleaned for kw in IMPORTANT_KEYWORDS):
                            found_keyword_early = True

                    print(f"   📸 {method_name}: {detected_count}個検出")

                    # 早期終了（施工状況とキーワードが見つかったら）
                    if FAST_MODE and found_status_early and found_keyword_early:
                        print(f"   ⚡ 早期終了（施工状況 + 重要キーワード取得）")
                        break

                except Exception as e:
                    print(f"   ⚠️  {method_name}でエラー: {e}")
                    continue

            print(f"\n   検出総数: {len(all_results)}個")

            # 優先順位別に格納
            status_texts = []
            important_keyword_texts = []
            high_confidence_texts = []

            # 信頼度順にソート
            sorted_results = sorted(all_results.items(), key=lambda x: x[1][0], reverse=True)

            for text, (confidence, method) in sorted_results:
                print(f"   📝 '{text}' (信頼度: {confidence:.2f}, 方法: {method})")

                # 1文字以下は除外
                if len(text) <= 1:
                    print(f"      ⏭️  短すぎる（1文字以下）")
                    continue

                # ラベル除去後テキスト
                stripped_text = strip_labels(text)

                if len(stripped_text) <= 1:
                    print(f"      ⏭️  ラベル除去後が短すぎる")
                    continue

                # 除外チェックを最優先
                if self.should_exclude_text(stripped_text):
                    print(f"      🚫 除外対象（除外キーワード一致）")
                    continue

                # 1. 施工前 / 施工中 / 施工後
                statuses = extract_statuses(stripped_text)
                if statuses:
                    print(f"      ⭐ 施工状況を採用: {statuses}")
                    for status in statuses:
                        if status not in status_texts:
                            status_texts.append(status)
                    continue

                # 2. 重要キーワード（全文ではなくキーワードだけ）
                keywords = extract_keywords(stripped_text)
                if keywords:
                    print(f"      ⭐⭐ 重要キーワードのみ採用: {keywords}")
                    for kw in keywords:
                        if kw not in important_keyword_texts:
                            important_keyword_texts.append(kw)
                    continue

                # 3. 高信頼度全文（0.70以上）
                if confidence >= HIGH_CONFIDENCE_THRESHOLD:
                    if not self.should_exclude_text(stripped_text):
                        print(f"      ⭐⭐⭐ 高信頼度({confidence:.2f}) → 全文採用")
                        if stripped_text not in high_confidence_texts:
                            high_confidence_texts.append(stripped_text)
                        continue
                    else:
                        print(f"      🚫 除外対象")
                        continue

                print(f"      ❌ 不採用")

            # 優先順位順で統合
            texts = status_texts + important_keyword_texts + high_confidence_texts

            # 優先順位を維持したまま重複・類似除去
            texts = dedupe_preserve_priority(texts)

            print(f"\n   📊 採用結果:")
            print(f"      🥇 施工状況: {status_texts}")
            print(f"      🥈 重要キーワード: {important_keyword_texts}")
            print(f"      🥉 高信頼度全文(0.70+): {high_confidence_texts}")
            print(f"      ✅ 最終採用順: {texts}\n")

            self.ocr_cache[image_path] = texts
            return texts

        except Exception as e:
            print(f"⚠️  OCRエラー: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def normalize_for_match(self, text):
        """比較用に正規化"""
        text = self.clean_ocr_text(text)
        text = re.sub(r'\s+', '', text)
        return text

    def find_best_label(self, text):
        """OCR文字列がどのラベルに近いか判定"""
        normalized = self.normalize_for_match(text)

        best_label = None
        best_score = 0.0

        for label in INFO_PANEL_LABELS:
            label_norm = re.sub(r'\s+', '', label)

            # 先頭付近だけで比較
            target = normalized[:len(label_norm) + 2]
            score = self.calculate_similarity(target, label_norm)

            # 完全包含なら優先
            if label_norm in normalized:
                return label

            if score > best_score:
                best_score = score
                best_label = label

        if best_score >= 0.55:
            return best_label

        return None

    def extract_labeled_panel_info(self, panel_texts):
        """情報板OCR結果から 工事件名 / 工事場所 / 施工状況 を抽出"""
        extracted = {}

        for text in panel_texts:
            cleaned = self.clean_ocr_text(text)
            compact = re.sub(r'\s+', '', cleaned)

            label = self.find_best_label(compact)
            if not label:
                continue

            label_norm = re.sub(r'\s+', '', label)

            # ラベル以降を値として切り出し
            value = compact
            idx = compact.find(label_norm)
            if idx != -1:
                value = compact[idx + len(label_norm):]

            value = value.strip()

            if not value:
                continue

            # OCR置換補正
            value = self.clean_ocr_text(value)

            # 施工状況だけはキーワード優先で丸める
            if label == "施工状況":
                for kw in IMPORTANT_KEYWORDS:
                    if kw in value:
                        value = kw
                        break

            extracted[label] = value

        return extracted

    def find_best_keyword_match(self, text, min_score=0.55):
        """OCR文字列を重要キーワードにあいまい一致させる"""
        cleaned = self.clean_ocr_text(text)
        normalized = re.sub(r'\s+', '', cleaned)

        best_keyword = None
        best_score = 0.0

        for keyword in IMPORTANT_KEYWORDS:
            keyword_norm = re.sub(r'\s+', '', keyword)

            # 完全一致・部分一致は優先
            if keyword_norm in normalized or normalized in keyword_norm:
                return keyword

            score = self.calculate_similarity(normalized, keyword_norm)
            if score > best_score:
                best_score = score
                best_keyword = keyword

        if best_score >= min_score:
            return best_keyword

        return None

    def extract_panel_keywords(self, panel_texts):
        """情報板OCR結果から重要キーワードを抽出（装置名向け）"""
        found = []

        for text in panel_texts:
            cleaned = self.clean_ocr_text(text)

            # まず完全一致・部分一致
            for keyword in IMPORTANT_KEYWORDS:
                if keyword in cleaned and keyword not in found:
                    found.append(keyword)

            # 次にあいまい一致
            matched_keyword = self.find_best_keyword_match(cleaned, min_score=0.58)
            if matched_keyword and matched_keyword not in found:
                found.append(matched_keyword)

        return found
            
    def remove_similar_texts(self, texts):
        """類似テキストを除去（優先順位を見てより良い方を残す）"""
        if not texts:
            return texts

        print(f"\n   🔄 類似テキスト除去処理:")
        print(f"      処理前: {len(texts)}個")

        result = []

        def normalize(text):
            text = self.clean_ocr_text(text)
            text = re.sub(r'\s+', '', text)
            return text

        def calc_priority(text):
            """
            類似テキスト同士でどちらを残すかの優先度
            - 施工前/中/後 は強く優先
            - IMPORTANT_KEYWORDS に近いものを優先
            - 除外対象は減点
            - 似た候補同士なら少し短い方を優先
              （誤OCRで1文字余計に入るケース対策）
            """
            norm = normalize(text)
            score = 0

            # 施工状況は強く優先
            if norm in ["施工前", "施工中", "施工後"]:
                score += 10000

            # 重要キーワード一致を優先
            for kw in IMPORTANT_KEYWORDS:
                kw_norm = re.sub(r'\s+', '', kw)

                if norm == kw_norm:
                    score += 8000 + len(kw_norm) * 100
                elif kw_norm in norm or norm in kw_norm:
                    score += 3000 + len(kw_norm) * 10

            # 除外対象は減点（ただし施工状況は除く）
            if self.should_exclude_text(norm) and norm not in ["施工前", "施工中", "施工後"]:
                score -= 5000

            # 類似候補同士では少し短い方を優先
            score -= len(norm)

            return score

        for text in texts:
            if not text:
                continue

            norm_text = normalize(text)
            if not norm_text:
                continue

            replaced = False
            skipped = False

            for i, adopted in enumerate(result):
                norm_adopted = normalize(adopted)

                similarity = self.calculate_similarity(norm_text, norm_adopted)
                is_included = (norm_text in norm_adopted) or (norm_adopted in norm_text)

                if similarity > 0.8 or is_included:
                    new_score = calc_priority(text)
                    old_score = calc_priority(adopted)

                    if new_score > old_score:
                        print(f"      🔄 '{adopted}' より '{text}' を優先 "
                              f"(類似: {similarity:.0%}, score {old_score} -> {new_score})")
                        result[i] = text
                        replaced = True
                    else:
                        print(f"      🚫 '{text}' は '{adopted}' と類似({similarity:.0%}) → 除外")
                        skipped = True
                    break

            if skipped:
                continue

            if not replaced:
                result.append(text)
                print(f"      ✅ '{text}' を採用")

        print(f"      処理後: {len(result)}個\n")
        return result
    
    def calculate_similarity(self, text1, text2):
        """レーベンシュタイン距離による類似度計算（0.0～1.0）"""
        if text1 == text2:
            return 1.0
        
        len1, len2 = len(text1), len(text2)
        
        # 長さが大きく異なる場合は類似度低い
        if abs(len1 - len2) > max(len1, len2) * 0.3:
            return 0.0
        
        # レーベンシュタイン距離計算
        if len1 < len2:
            text1, text2 = text2, text1
            len1, len2 = len2, len1
        
        current_row = range(len2 + 1)
        for i in range(1, len1 + 1):
            previous_row, current_row = current_row, [i] + [0] * len2
            for j in range(1, len2 + 1):
                add, delete, change = previous_row[j] + 1, current_row[j-1] + 1, previous_row[j-1]
                if text1[i-1] != text2[j-1]:
                    change += 1
                current_row[j] = min(add, delete, change)
        
        distance = current_row[len2]
        max_len = max(len1, len2)
        similarity = 1.0 - (distance / max_len)
        
        return similarity            
    
    def clean_ocr_text(self, text):
        """OCRテキストをクリーニング"""
        # OCR誤認識修正
        for old, new in OCR_REPLACEMENTS.items():
            text = text.replace(old, new)
        
        # 除外文字を削除
        for char in EXCLUDE_CHARS:
            text = text.replace(char, EXCLUDE_CHAR_REPLACEMENT)
        
        return text.strip()
    
    def should_exclude_text(self, text):
        """テキストを除外すべきかチェック"""
        # 除外単語チェック
        for word in EXCLUDE_WORDS:
            if word in text:
                return True
        
        # 除外パターンチェック
        for pattern in EXCLUDE_PATTERNS:
            if re.match(pattern, text):
                return True
        
        return False
    
    def extract_filename_parts(self, text, confidence=0.0):
        """
        ファイル名用にOCR文字列を分解する

        ルール:
        1. 施工前/施工中/施工後 が含まれていたら、それを残す（信頼度無視）
        2. 重要キーワードが含まれていたら、そのキーワードだけ残す
        3. 上記が無く、かつ除外語を含む場合は捨てる
        4. 上記が無く、信頼度が KEEP_CONFIDENCE_THRESHOLD 以上なら全文を残す
        5. 工事場所 / 施工状況 / 工事件名 は除去
        """
        cleaned = self.clean_ocr_text(text)
        cleaned = re.sub(r'\s+', '', cleaned).strip()

        if not cleaned:
            return []

        # ラベル語は不要
        for label in INFO_PANEL_LABELS:
            cleaned = cleaned.replace(label, '')

        cleaned = cleaned.strip()
        if not cleaned:
            return []

        result = []

        # 1) 施工前/中/後 は無条件採用
        for status in ["施工前", "施工中", "施工後"]:
            if status in cleaned and status not in result:
                result.append(status)

        # 2) 重要キーワードは「その語だけ」採用
        for kw in IMPORTANT_KEYWORDS:
            kw_clean = re.sub(r'\s+', '', self.clean_ocr_text(kw))
            if kw_clean and kw_clean in cleaned and kw not in result:
                result.append(kw)

        # キーワードまたは施工状況が見つかったら、それだけ返す
        if result:
            return result

        # 3) 除外語が含まれていて、重要キーワードが無い場合は捨てる
        for word in EXCLUDE_WORDS:
            if word and word in cleaned:
                return []

        # 4) 高信頼度なら全文採用
        if confidence >= KEEP_CONFIDENCE_THRESHOLD:
            if self.should_exclude_text(cleaned):
                return []
            return [cleaned]

        return []
    
    def extract_important_keywords(self, texts):
        """重要キーワードのみ抽出"""
        if not texts:
            return []
        
        if not IMPORTANT_KEYWORDS:
            return texts
        
        important_texts = []
        
        print(f"🔍 重要キーワードマッチング:")
        for text in texts:
            matched = False
            
            for keyword in IMPORTANT_KEYWORDS:
                if keyword in text:
                    print(f"   ⭐ '{text}' ← キーワード: '{keyword}'")
                    important_texts.append(text)
                    matched = True
                    break
            
            if not matched:
                print(f"   ⏭️  '{text}' (マッチなし)")
        
        seen = set()
        result = []
        for text in important_texts:
            if text not in seen:
                seen.add(text)
                result.append(text)
        
        print(f"   📊 最終: {result}\n")
        
        return result

    def generate_new_name(self, filepath, file_date):
        """新しいファイル名を生成"""
        base_name = PREFIX

        if INCLUDE_DATE and file_date:
            date_str = file_date.strftime('%Y%m%d')
            base_name = f"{date_str}_{base_name}"

        filename_parts = []
        protected_parts = set()  # 後段の除外で落としたくない語

        def normalize_part(text):
            text = self.clean_ocr_text(text)
            text = re.sub(r'\s+', '', text)
            return text.strip()

        def add_part(part, protect=False):
            """ファイル名候補を追加（重複・包含を整理）"""
            if not part:
                return

            part = normalize_part(part)

            if not part:
                return

            if part in INFO_PANEL_LABELS:
                return

            # 既存候補との重複・包含を整理
            for i, existing in enumerate(filename_parts):
                if part == existing:
                    if protect:
                        protected_parts.add(existing)
                    return

                # 新しい候補が既存候補に含まれているなら不要
                if part in existing:
                    if protect:
                        protected_parts.add(existing)
                    return

                # 既存候補が新しい候補に含まれるなら、より長い新候補で置換
                if existing in part:
                    old_existing = filename_parts[i]
                    filename_parts[i] = part

                    if old_existing in protected_parts:
                        protected_parts.remove(old_existing)
                        protected_parts.add(part)
                    elif protect:
                        protected_parts.add(part)

                    return

            filename_parts.append(part)
            if protect:
                protected_parts.add(part)

        if USE_OCR and ADD_OCR_TEXT:
            # 通常OCR
            texts = self.perform_ocr(filepath)

            # 情報板OCR
            panel_texts = []
            if USE_INFO_PANEL_OCR:
                panel_texts = self.perform_info_panel_ocr(filepath)

            # === 【新規追加】重要キーワードを信頼度無視で強制抽出 ===
            important_keywords = self.config.get('IMPORTANT_KEYWORDS', [])
            if not important_keywords:
                important_keywords = IMPORTANT_KEYWORDS
            
            # 全OCR結果から重要キーワードを検索
            all_ocr_text = ' '.join(texts + panel_texts)
            for kw in important_keywords:
                if kw in all_ocr_text:
                    add_part(kw, protect=True)
                    print(f"   🔑 [重要キーワード強制抽出] {kw}")            

            # ラベル情報抽出
            labeled_info = self.extract_labeled_panel_info(panel_texts)

            # 情報板から重要キーワード抽出
            panel_keywords = self.extract_panel_keywords(panel_texts)

            print(f"   🏷️ ラベル抽出結果: {labeled_info}")
            print(f"   🔑 情報板キーワード抽出結果: {panel_keywords}")

            # 1. 施工状況
            if "施工状況" in labeled_info and labeled_info["施工状況"]:
                add_part(labeled_info["施工状況"], protect=True)

            # 2. 情報板キーワード（装置名など + 施工前/中/後）
            for kw in panel_keywords:
                add_part(kw, protect=True)  # ← 修正：条件削除

            # 3. 通常OCRから補完
            for t in texts:
                cleaned_t = normalize_part(t)
                if not cleaned_t:
                    continue

                is_status = cleaned_t in ["施工前", "施工中", "施工後"]
                has_important_keyword = any(
                    re.sub(r'\s+', '', kw) in cleaned_t
                    for kw in IMPORTANT_KEYWORDS
                )

                if USE_FULL_OCR_TEXT:
                    # フルOCR利用時:
                    # - 重要キーワードを含む
                    # - 施工前/中/後
                    # - 除外対象でない
                    # のいずれかなら追加
                    if has_important_keyword or is_status or not self.should_exclude_text(cleaned_t):
                        add_part(cleaned_t, protect=(has_important_keyword or is_status))
                else:
                    # フルOCR未使用時は重要語だけ
                    if has_important_keyword or is_status:
                        add_part(cleaned_t, protect=True)

        print(f"   🧪 filename_parts(フィルタ前): {filename_parts}")

        # 不要語除外
        filtered_parts = []
        for part in filename_parts:
            if not part:
                continue

            part = normalize_part(part)
            if not part:
                continue

            # ラベルそのものは入れない
            if part in INFO_PANEL_LABELS:
                continue

            # 2文字未満除外
            if len(part) < 2:
                continue

            is_status = part in ["施工前", "施工中", "施工後"]
            has_important_keyword = any(
                re.sub(r'\s+', '', kw) in part
                for kw in IMPORTANT_KEYWORDS
            )
            is_protected = part in protected_parts

            # protected / 重要キーワード / 施工状況 は落とさない
            if self.should_exclude_text(part):
                if not (is_status or has_important_keyword or is_protected):
                    print(f"      🚫 filtered_partsで除外: {part}")
                    continue

            # 重複除去
            if part not in filtered_parts:
                filtered_parts.append(part)

        print(f"   🧪 filtered_parts(最終): {filtered_parts}")

        if filtered_parts:
            ocr_part = '_'.join(filtered_parts[:8])
            base_name = f"{base_name}_{ocr_part}"

        # === 【新規追加】除外キーワードを最後に適用 ===
        exclude_words = self.config.get('EXCLUDE_WORDS', [])
        if exclude_words:
            for exclude in exclude_words:
                if exclude in base_name:
                    base_name = base_name.replace(exclude, '')
                    print(f"      🚫 [除外キーワード削除] {exclude}")
            
            # 連続するアンダースコアを1つに
            base_name = re.sub(r'_+', '_', base_name)
            # 先頭・末尾のアンダースコアを削除
            base_name = base_name.strip('_')

        if len(base_name) > MAX_FILENAME_LENGTH:
            base_name = base_name[:MAX_FILENAME_LENGTH]

        ext = os.path.splitext(filepath)[1]
        return f"{base_name}{ext}"

    def generate_preview(self):
        """リネームプレビューを生成"""
        file_dates = []
        for filepath in self.files:
            file_date = self.get_file_date(filepath)
            file_dates.append((filepath, file_date))

        if SORT_BY_DATE:
            file_dates.sort(key=lambda x: x[1] if x[1] else datetime.min)

        preview_data = []

        if CLASSIFY_BY_NAME:
            groups = {}
            for filepath, file_date in file_dates:
                new_name_base = self.generate_new_name(filepath, file_date)
                name_without_ext = os.path.splitext(new_name_base)[0]

                if name_without_ext not in groups:
                    groups[name_without_ext] = []

                groups[name_without_ext].append((filepath, file_date))

            for name_base, group_files in groups.items():
                for i, (filepath, file_date) in enumerate(group_files, start=START_NUMBER):
                    ext = os.path.splitext(filepath)[1]
                    number_str = str(i).zfill(DIGIT_COUNT)
                    new_name = f"{name_base}_{number_str}{ext}"
                    preview_data.append((filepath, new_name))
        else:
            for i, (filepath, file_date) in enumerate(file_dates, start=START_NUMBER):
                new_name = self.generate_new_name(filepath, file_date)
                ext = os.path.splitext(filepath)[1]
                number_str = str(i).zfill(DIGIT_COUNT)
                base = os.path.splitext(new_name)[0]
                new_name = f"{base}_{number_str}{ext}"
                preview_data.append((filepath, new_name))

        return preview_data

    def rename_files_from_preview(self, preview_data):
        """プレビューデータからリネーム実行"""
        renamed_count = 0
        
        for old_path, new_name in preview_data:
            new_path = os.path.join(os.path.dirname(old_path), new_name)
            
            try:
                os.rename(old_path, new_path)
                print(f"✅ {os.path.basename(old_path)} → {new_name}")
                renamed_count += 1
            except Exception as e:
                print(f"❌ リネーム失敗: {old_path} - {e}")
        
        print(f"\n✅ リネーム完了: {renamed_count}/{len(preview_data)}ファイル")
    
    def rename_files(self):
        """ファイルをリネーム"""
        # OCR初期化
        if USE_OCR:
            self.initialize_ocr()
        
        # ファイルと日付のペアを作成
        file_dates = []
        for filepath in self.files:
            file_date = self.get_file_date(filepath)
            file_dates.append((filepath, file_date))
        
        # 日付順にソート
        if SORT_BY_DATE:
            file_dates.sort(key=lambda x: x[1] if x[1] else datetime.min)
        
        # 名前でグループ化
        if CLASSIFY_BY_NAME:
            groups = {}
            for filepath, file_date in file_dates:
                new_name_base = self.generate_new_name(filepath, file_date)
                name_without_ext = os.path.splitext(new_name_base)[0]
                
                if name_without_ext not in groups:
                    groups[name_without_ext] = []
                
                groups[name_without_ext].append((filepath, file_date))
            
            # 各グループに連番を付与
            renamed_count = 0
            for name_base, group_files in groups.items():
                for i, (filepath, file_date) in enumerate(group_files, start=START_NUMBER):
                    ext = os.path.splitext(filepath)[1]
                    number_str = str(i).zfill(DIGIT_COUNT)
                    new_name = f"{name_base}_{number_str}{ext}"
                    
                    # リネーム実行
                    new_path = os.path.join(os.path.dirname(filepath), new_name)
                    
                    try:
                        os.rename(filepath, new_path)
                        print(f"✅ {os.path.basename(filepath)} → {new_name}")
                        renamed_count += 1
                    except Exception as e:
                        print(f"❌ リネーム失敗: {filepath} - {e}")
            
            print(f"\n✅ リネーム完了: {renamed_count}/{len(self.files)}ファイル")
        
        else:
            # グループ化なし
            renamed_count = 0
            for i, (filepath, file_date) in enumerate(file_dates, start=START_NUMBER):
                new_name = self.generate_new_name(filepath, file_date)
                ext = os.path.splitext(filepath)[1]
                number_str = str(i).zfill(DIGIT_COUNT)
                base = os.path.splitext(new_name)[0]
                new_name = f"{base}_{number_str}{ext}"
                
                # リネーム実行
                new_path = os.path.join(os.path.dirname(filepath), new_name)
                
                try:
                    os.rename(filepath, new_path)
                    print(f"✅ {os.path.basename(filepath)} → {new_name}")
                    renamed_count += 1
                except Exception as e:
                    print(f"❌ リネーム失敗: {filepath} - {e}")
            
            print(f"\n✅ リネーム完了: {renamed_count}/{len(self.files)}ファイル")


def main():
    """メイン処理"""
    print("=" * 60)
    print("📷 画像一括リネームツール (EasyOCR + Tesseract 複合版)")
    print("=" * 60)
    
    # コマンドライン引数からファイルを取得
    if len(sys.argv) > 1:
        # ドラッグ&ドロップされたファイル
        files = []
        for arg in sys.argv[1:]:
            if os.path.isfile(arg):
                ext = os.path.splitext(arg)[1].lower()
                if ext in ('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff'):
                    files.append(arg)
        
        if not files:
            print("❌ 有効な画像ファイルが選択されていません")
            input("\nEnterキーを押して終了...")
            return
    else:
        # 引数なしの場合はカレントディレクトリ
        current_dir = os.getcwd()
        image_extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff')
        
        files = [
            os.path.join(current_dir, f)
            for f in os.listdir(current_dir)
            if f.lower().endswith(image_extensions)
        ]
        
        if not files:
            print("❌ 画像ファイルが見つかりません")
            input("\nEnterキーを押して終了...")
            return
    
    print(f"\n📁 対象ファイル: {len(files)}個")
    
    # ディレクトリ表示
    if files:
        target_dir = os.path.dirname(files[0]) if len(files) == 1 else os.path.commonpath(files)
        print(f"📍 対象ディレクトリ: {target_dir}")
    
    # 設定表示
    print(f"\n⚙️  設定:")
    print(f"  プレフィックス: {PREFIX}")
    print(f"  日付を含める: {INCLUDE_DATE}")
    print(f"  名前でグループ化: {CLASSIFY_BY_NAME}")
    print(f"  EXIF日付使用: {USE_EXIF_DATE}")
    print(f"  日付順ソート: {SORT_BY_DATE}")
    print(f"  OCR使用: {USE_OCR}")
    
    if USE_OCR:
        print(f"  EasyOCR使用: {USE_EASYOCR}")
        print(f"  Tesseract使用: {USE_TESSERACT}")
        print(f"  OCRテキスト追加: {ADD_OCR_TEXT}")
        print(f"  フルテキスト使用: {USE_FULL_OCR_TEXT}")
        print(f"  信頼度閾値: {OCR_CONFIDENCE_THRESHOLD}")
        print(f"  モデルディレクトリ: {OCR_MODEL_DIR}")
    
    # プレビュー生成
    print("\n" + "=" * 60)
    print("🔍 リネーム後のファイル名をプレビュー中...")
    print("=" * 60)
    
    renamer = ImageRenamer(files)
    
    # OCR初期化
    if USE_OCR:
        renamer.initialize_ocr()
    
    # プレビューデータ生成
    preview_data = renamer.generate_preview()
    
    # プレビュー表示
    print("\n📋 リネームプレビュー:")
    print("-" * 60)
    for i, (old_path, new_name) in enumerate(preview_data, 1):
        old_name = os.path.basename(old_path)
        print(f"{i}. {old_name}")
        print(f"   → {new_name}")
        print()
    
    # 実行確認
    print("=" * 60)
    response = input("⚠️  このままリネームを実行しますか？ (yes/no): ").strip().lower()
    
    if response not in ['yes', 'y']:
        print("❌ キャンセルしました")
        input("\nEnterキーを押して終了...")
        return
    
    # リネーム実行
    print("\n🚀 リネーム開始...")
    print("=" * 60)
    
    renamer.rename_files_from_preview(preview_data)
    
    print("=" * 60)
    print("✅ 処理完了")
    input("\nEnterキーを押して終了...")


if __name__ == "__main__":
    main()
