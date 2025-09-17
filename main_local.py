# =============================================================================
# Step 1: 匯入必要模組與自訂函式
# =============================================================================
# 匯入標準函式庫，如 OpenCV 用於影像處理、argparse 用於解析命令列參數、
# numpy 用於數值運算、time 用於時間控制、copy 用於物件複製、
# PIL (Pillow) 用於處理中文字體、collections.Counter 用於計數。
# 同時，從專案的 utils 目錄下匯入自訂的核心功能，包括：
# - add_common_arguments: 添加通用的命令列參數。
# - initialize_camera: 初始化攝影機。
# - initialize_arm_controller: 初始化機械手臂控制器。
# - process_frame_and_control_arm: 處理單一畫格並控制手臂。
# - cleanup_resources: 程式結束時釋放資源。
# - StateManager: 狀態管理器。
# - vision_config: 視覺處理相關的設定檔。
# - draw_chinese_text: 在影像上繪製中文文字的輔助函式。
import cv2
import argparse
import numpy as np
import time
from copy import deepcopy
from PIL import ImageFont
from collections import Counter

from utils.app_core import (
    add_common_arguments, 
    initialize_camera, 
    initialize_arm_controller, 
    process_frame_and_control_arm,
    cleanup_resources,
    StateManager 
)
from utils.vision_processing import config as vision_config
from utils.vision_processing.ui_basic import draw_chinese_text

# =============================================================================
# Step 2: 定義全域變數與 UI 參數
# =============================================================================
# 定義整個應用程式會共用的全域變數。
# - CANVAS_H, CANVAS_W: 主 UI 畫布的高度與寬度。
# - current_color_to_adjust: 當前正在透過 UI 調整的顏色名稱 (例如 "Red")。
# - current_action_from_buttons: 儲存最近一次按鈕點擊的動作。
# - live_color_ranges: 儲存即時的 HSV 顏色範圍，可在 UI 中動態調整。
# - hsv_values: 當前正在調整的顏色的 HSV 上下限值。
# - dragging: 用於標記滑鼠是否正在拖曳 HSV 滑塊。
# - ui_enabled: 控制是否顯示互動式 UI。
# - hovered_button_idx: 記錄滑鼠目前懸停在哪個按鈕上，以實現 hover 效果。
# - save_feedback_end_time: 控制 "儲存成功" 訊息的顯示時間。
#
# 同時定義 UI 介面的外觀參數，如按鈕的尺寸、顏色、文字，以及 HSV 滑動條的位置和大小。
CANVAS_H = 900
CANVAS_W = 1280
current_color_to_adjust = "Red"
current_action_from_buttons = None
live_color_ranges = {}
hsv_values = [[0,0,0],[179,255,255]]
dragging = None  # (idx, min_or_max) or None
ui_enabled = True  # 預設開啟UI
hovered_button_idx = None  # 新增：目前 hover 的按鈕編號
save_feedback_end_time = 0 # 新增：用來控制儲存成功訊息的顯示時間

# --- UI 參數 ---
BUTTON_HEIGHT = 30
BUTTON_WIDTH = 180
TEXT_COLOR = (255, 255, 255)
BUTTON_COLOR = (100, 100, 100) # 灰色按鈕
AUTO_BOTTON_COLOR = (0, 150, 0)  # 綠色按鈕
QUIT_BUTTON_COLOR = (50, 50, 150) # 紅色案紐
buttons_config = [
    {"text": "調整紅色", "action": "set_red", "color": BUTTON_COLOR, "text_color": TEXT_COLOR},
    {"text": "調整藍色", "action": "set_blue", "color": BUTTON_COLOR, "text_color": TEXT_COLOR},
    {"text": "調整綠色", "action": "set_green", "color": BUTTON_COLOR, "text_color": TEXT_COLOR},
    {"text": "儲存設定", "action": "save", "color": BUTTON_COLOR, "text_color": TEXT_COLOR},
    {"text": "自動模式", "action": "auto_mode", "color": AUTO_BOTTON_COLOR, "text_color": TEXT_COLOR},
    {"text": "選擇鏡頭", "action": "select_camera", "color": BUTTON_COLOR, "text_color": TEXT_COLOR},  
    {"text": "離開", "action": "quit", "color": QUIT_BUTTON_COLOR, "text_color": TEXT_COLOR},
]
# HSV條參數
HSV_BAR_X = 970
HSV_BAR_Y = 60
HSV_BAR_W = 250
HSV_BAR_H = 20
HSV_BAR_GAP = 50

# =============================================================================
# Step 3: HSV 調整面板繪製 (此函式目前未被使用，由 draw_combined_ui 取代)
# =============================================================================
# `draw_hsv_panel` 函式用於建立一個獨立的 HSV 調整面板。
# 它會在一個小的 numpy 畫布上顯示當前正在調整的顏色名稱 (H, S, V) 的
# 最小值 (min) 和最大值 (max)。
# 注意：在目前的版本中，這個獨立的面板功能已經被整合到 `draw_combined_ui`
# 的滑動條介面中，因此這個函式實際上沒有被呼叫。
def draw_hsv_panel(hsv_values, current_color):
    panel = np.full((180, 320, 3), 80, dtype=np.uint8)
    cv2.putText(panel, f"HSV Adjust ({current_color})", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,255,0), 2)
    labels = ["H", "S", "V"]
    for i, l in enumerate(labels):
        y = 60 + i*35
        cv2.putText(panel, f"{l}_min: {hsv_values[0][i]:3d}", (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 1)
        cv2.putText(panel, f"{l}_max: {hsv_values[1][i]:3d}", (160, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 1)
    return panel

# =============================================================================
# Step 4: 按鈕面板繪製
# =============================================================================
# `draw_buttons_panel_img` 函式負責繪製右側的控制面板。
# 這個面板包含了所有可操作的按鈕，例如 "調整紅色"、"儲存設定"、"自動模式" 等。
# 功能包括：
# - 根據 `buttons_config` 動態生成按鈕。
# - 顯示目前正在調整的目標顏色，或在儲存後顯示 "儲存成功！" 的回饋訊息。
# - 處理按鈕的 hover 效果，當滑鼠懸停在按鈕上時會改變顏色。
# - 使用 `draw_chinese_text` 函式來確保按鈕上的中文能夠正確顯示。
def draw_buttons_panel_img(current_color, panel_w=320, panel_h=None):
    global hovered_button_idx, save_feedback_end_time
    # 英文顏色對應中文
    color_map = {"Red": "紅色", "Blue": "藍色", "Green": "綠色"}
    btn_count = len(buttons_config)
    btn_h = 40
    btn_gap = 15
    top_margin = 50
    bottom_margin = 20
    if panel_h is None:
        panel_h = top_margin + btn_count * btn_h + (btn_count - 1) * btn_gap + bottom_margin
    panel = np.full((panel_h, panel_w, 3), (220, 220, 220), dtype=np.uint8)

    # 檢查是否要顯示儲存成功訊息
    if time.time() < save_feedback_end_time:
        adjust_text = "儲存成功！"
    else:
        # 中文顏色顯示
        ch_color = color_map.get(current_color, current_color)
        adjust_text = f"調整目標：{ch_color}"

    # 置中計算
    font_size = 28
    font_path = "chinese.ttf"
    # 先用 PIL 計算文字寬度
    font = ImageFont.truetype(font_path, font_size)
    bbox = font.getbbox(adjust_text)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    text_x = (panel_w - text_w) // 2
    text_y = 15
    panel = draw_chinese_text(panel, adjust_text, (text_x, text_y), font_size=font_size, color=(0,0,0), font_path=font_path)

    btn_w = int(panel_w * 0.75)
    btn_x = int((panel_w - btn_w) / 2)
    btn_y = top_margin
    for idx, button in enumerate(buttons_config):
        y = btn_y + idx * (btn_h + btn_gap)
        color = button["color"]
        # hover 時變色
        if hovered_button_idx == idx:
            # 這裡用簡單的對比色（可自行調整）
            color = (min(color[0]+80,255), min(color[1]+80,255), min(color[2]+80,255))
        cv2.rectangle(panel, (btn_x, y), (btn_x + btn_w, y + btn_h), color, -1)
        # 置中計算
        font_size_btn = 22
        font_btn = ImageFont.truetype(font_path, font_size_btn)
        bbox_btn = font_btn.getbbox(button["text"])
        text_w_btn, text_h_btn = bbox_btn[2] - bbox_btn[0], bbox_btn[3] - bbox_btn[1]
        text_x_btn = btn_x + (btn_w - text_w_btn) // 2
        text_y_btn = y + (btn_h - text_h_btn) // 2
        panel = draw_chinese_text(
            panel,
            button["text"],
            (text_x_btn, text_y_btn),
            font_size=font_size_btn,
            color=button.get("text_color", (0,0,0)),
            font_path=font_path
        )
    return panel

# =============================================================================
# Step 5: 主 UI 組合
# =============================================================================
# `draw_combined_ui` 是整個互動介面的核心繪圖函式。
# 它會建立一個大的白色畫布，並將各個 UI 元件組合在一起，包括：
# - 左上角：顯示即時的攝影機影像。
# - 左下角：顯示當前顏色過濾後的二值化遮罩 (mask)。
# - 右側上方：繪製 HSV 滑動條，用於即時調整 H, S, V 的上下限。
# - 右側下方：嵌入由 `draw_buttons_panel_img` 產生的控制面板。
# - 左上角（疊加）：如果處於模擬辨識模式，會顯示辨識物體的計數器。
# 整個函式使用相對座標來定位各個元件，使得調整整體視窗大小變得更容易。
def draw_combined_ui(main_img, hsv_values, current_color, mask=None, label_counter=None):
    canvas_h, canvas_w = CANVAS_H, CANVAS_W
    canvas = np.full((canvas_h, canvas_w, 3), 255, dtype=np.uint8)  # 背景白色

    # 相對位置與大小
    main_x = int(canvas_w * 0.015)
    main_y = int(canvas_h * 0.028)
    main_w = int(canvas_w * 0.7)
    main_h = int(canvas_h * 0.47)

    mask_x = main_x
    mask_y = main_y + main_h + int(canvas_h * 0.02)
    mask_w = main_w
    mask_h = main_h

    hsv_panel_x = int(canvas_w * 0.75)
    hsv_panel_y = int(canvas_h * 0.08)  # 互動區一致
    hsv_panel_w = int(canvas_w * 0.22)
    hsv_panel_h = int(canvas_h * 0.25)

    ctrl_panel_x = hsv_panel_x
    ctrl_panel_y = int(canvas_h * 0.40)  # 原本是 0.48，往上移一點

    # 左上主畫面
    main_img_resized = cv2.resize(main_img, (main_w, main_h))
    canvas[main_y:main_y+main_h, main_x:main_x+main_w] = main_img_resized
    canvas = draw_chinese_text(canvas, "攝影機", (main_x+10, main_y+10), font_size=32, color=(255,255,255))

    # 左下mask
    if mask is not None:
        mask_color = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR) if len(mask.shape)==2 else mask
        mask_resized = cv2.resize(mask_color, (mask_w, mask_h))
        canvas[mask_y:mask_y+mask_h, mask_x:mask_x+mask_w] = mask_resized
        canvas = draw_chinese_text(canvas, "遮罩", (mask_x+10, mask_y+15), font_size=32, color=(255,255,255))

    # 右上HSV panel
    # 將 "HSV調整" 文字往上提 15px
    canvas = draw_chinese_text(canvas, "HSV調整", (hsv_panel_x, hsv_panel_y - 15), font_size=28, color=(0,0,0))
    cv2.rectangle(canvas, (hsv_panel_x, hsv_panel_y+10), (hsv_panel_x+hsv_panel_w, hsv_panel_y+10+hsv_panel_h), (220,220,220), -1)  # 淡灰
    labels = ["H", "S", "V"]
    maxs = [179, 255, 255]
    bar_x = hsv_panel_x + int(hsv_panel_w * 0.07)
    bar_w = int(hsv_panel_w * 0.8)
    bar_h = int(hsv_panel_h * 0.13)
    for i, l in enumerate(labels):
        y = hsv_panel_y + 40 + i*int(hsv_panel_h * 0.28)
        cv2.rectangle(canvas, (bar_x, y), (bar_x+bar_w, y+bar_h), (180,180,180), -1)  # 更淡灰
        vmin = int(hsv_values[0][i]/maxs[i]*bar_w)
        vmax = int(hsv_values[1][i]/maxs[i]*bar_w)
        cv2.rectangle(canvas, (bar_x+vmin, y), (bar_x+vmax, y+bar_h), (0,0,0), -1)  # 黑色區間
        cv2.rectangle(canvas, (bar_x+vmin-5, y-5), (bar_x+vmin+5, y+bar_h+5), (50,50,50), -1)  # 深灰滑塊
        cv2.rectangle(canvas, (bar_x+vmax-5, y-5), (bar_x+vmax+5, y+bar_h+5), (100,100,100), -1)  # 深灰滑塊
        cv2.putText(canvas, f"{l}_min:{hsv_values[0][i]:3d}", (bar_x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,0,0), 1)
        cv2.putText(canvas, f"{l}_max:{hsv_values[1][i]:3d}", (bar_x+int(bar_w*0.6), y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,0,0), 1)

    # 右下Control panel
    ctrl_panel = draw_buttons_panel_img(current_color, panel_w=hsv_panel_w)
    ctrl_h, ctrl_w = ctrl_panel.shape[:2]
    cv2.rectangle(canvas, (ctrl_panel_x, ctrl_panel_y), (ctrl_panel_x+ctrl_w, ctrl_panel_y+ctrl_h), (220,220,220), -1)
    canvas = draw_chinese_text(canvas, "控制面板", (ctrl_panel_x, ctrl_panel_y - 35), font_size=28, color=(0,0,0))
    # 修正：確保不超出 canvas
    y1 = int(ctrl_panel_y)
    y2 = min(y1 + ctrl_h, canvas.shape[0])
    x1 = int(ctrl_panel_x)
    x2 = min(x1 + ctrl_w, canvas.shape[1])
    panel_crop = ctrl_panel[:y2-y1, :x2-x1]
    canvas[y1:y2, x1:x2] = panel_crop

    # 顯示計數器內容（左上角）
    if label_counter is not None and len(label_counter) > 0:
        counter_text = "計數器："
        x_base = 30
        y_base = 110  # 往下移動一點（原本是60）
        canvas = draw_chinese_text(canvas, counter_text, (x_base, y_base), font_size=28, color=(0,0,255))
        for i, (label, count) in enumerate(label_counter.most_common()):
            text = f"{label}: {count}"
            canvas = draw_chinese_text(canvas, text, (x_base, y_base + 35 + i*32), font_size=26, color=(0,0,180))

    # 顯示模式
    # mode_text = f"模式：{'一般' if current_mode == MODE_AUTO else '模擬'}"
    # canvas = draw_chinese_text(canvas, mode_text, (30, 70), font_size=28, color=(0,128,255))

    return canvas

# =============================================================================
# Step 6: 處理滑鼠事件
# =============================================================================
# `on_all_in_one_mouse` 是設定給主 OpenCV 視窗的滑鼠回呼函式。
# 它負責處理所有在 "ARMCtrl-ALL-IN-ONE" 視窗內的滑鼠互動，主要功能有：
# - 按鈕點擊：當滑鼠左鍵點擊在某個按鈕的範圍內時，更新 `current_action_from_buttons`
#   全域變數，觸發主迴圈中對應的動作。
# - 按鈕懸停：當滑鼠移動到按鈕上時，更新 `hovered_button_idx` 以觸發 hover 視覺效果。
# - HSV 滑塊拖曳：
#   - LBUTTONDOWN: 偵測滑鼠是否點擊在 HSV 滑塊上，並記錄正在拖曳的目標 (H/S/V 的 min/max)。
#   - MOUSEMOVE: 如果正在拖曳，根據滑鼠的 X 座標更新對應的 HSV 值。
#   - LBUTTONUP: 結束拖曳狀態。
def on_all_in_one_mouse(event, x, y, flags, param):
    global current_action_from_buttons, dragging, hsv_values, hovered_button_idx
    canvas_h, canvas_w = CANVAS_H, CANVAS_W
    hsv_panel_w = int(canvas_w * 0.22)
    ctrl_panel_x = int(canvas_w * 0.75)
    ctrl_panel_y = int(canvas_h * 0.40)  # 必須和 draw_combined_ui 一致
    panel_w = hsv_panel_w
    # 與 draw_buttons_panel_img 保持一致
    btn_count = len(buttons_config)
    btn_h = 40
    btn_gap = 15
    top_margin = 50
    bottom_margin = 20
    panel_h = top_margin + btn_count * btn_h + (btn_count - 1) * btn_gap + bottom_margin
    btn_w = int(panel_w * 0.75)
    btn_x = int((panel_w - btn_w) / 2)
    btn_y = top_margin
    hovered = None
    for idx, button in enumerate(buttons_config):
        y_btn = btn_y + idx * (btn_h + btn_gap)
        abs_x1 = ctrl_panel_x + btn_x
        abs_y1 = ctrl_panel_y + y_btn
        abs_x2 = abs_x1 + btn_w
        abs_y2 = abs_y1 + btn_h
        if event == cv2.EVENT_LBUTTONDOWN:
            if abs_x1 <= x < abs_x2 and abs_y1 <= y < abs_y2:
                current_action_from_buttons = button["action"]
                return
        if event == cv2.EVENT_MOUSEMOVE:
            if abs_x1 <= x < abs_x2 and abs_y1 <= y < abs_y2:
                hovered = idx
    if event == cv2.EVENT_MOUSEMOVE:
        if hovered_button_idx != hovered:
            hovered_button_idx = hovered

    # HSV滑動條互動區（完全用相對座標）
    hsv_panel_x = int(canvas_w * 0.75)
    hsv_panel_y = int(canvas_h * 0.08)
    hsv_panel_w = int(canvas_w * 0.22)
    hsv_panel_h = int(canvas_h * 0.25)
    bar_x = hsv_panel_x + int(hsv_panel_w * 0.07)
    bar_w = int(hsv_panel_w * 0.8)
    bar_h = int(hsv_panel_h * 0.13)
    for i in range(3):
        y_bar = hsv_panel_y + 40 + i*int(hsv_panel_h * 0.28)
        min_rect = (bar_x+int(hsv_values[0][i]/[179,255,255][i]*bar_w)-5, y_bar-5,
                    bar_x+int(hsv_values[0][i]/[179,255,255][i]*bar_w)+5, y_bar+bar_h+5)
        max_rect = (bar_x+int(hsv_values[1][i]/[179,255,255][i]*bar_w)-5, y_bar-5,
                    bar_x+int(hsv_values[1][i]/[179,255,255][i]*bar_w)+5, y_bar+bar_h+5)
        if event == cv2.EVENT_LBUTTONDOWN:
            if min_rect[0] <= x <= min_rect[2] and min_rect[1] <= y <= min_rect[3]:
                dragging = (i, 'min')
                return
            if max_rect[0] <= x <= max_rect[2] and max_rect[1] <= y <= max_rect[3]:
                dragging = (i, 'max')
                return
        elif event == cv2.EVENT_LBUTTONUP:
            dragging = None
        elif event == cv2.EVENT_MOUSEMOVE and dragging is not None and flags & cv2.EVENT_FLAG_LBUTTON:
            idx, which = dragging
            rel = x - bar_x
            rel = max(0, min(bar_w, rel))
            value = int(rel/max(1,bar_w)*[179,255,255][idx])
            if which == 'min':
                hsv_values[0][idx] = min(value, hsv_values[1][idx]-1)
            else:
                hsv_values[1][idx] = max(value, hsv_values[0][idx]+1)

# =============================================================================
# Step 7: 進入自動模式前的確認視窗
# =============================================================================
# `show_auto_mode_confirm` 函式會在使用者點擊 "自動模式" 按鈕後觸發。
# 它會彈出一個獨立的確認視窗，顯示目前設定的所有顏色的 HSV 範圍，並提示使用者
# 進入自動模式後將是無 UI 的持續辨識狀態。
# 使用者可以點擊 "確認" 進入無 UI 模式，或點擊 "取消" 返回到原本的互動介面。
# 這個視窗也支援按鈕的 hover 效果和透過 Esc 鍵或關閉按鈕來取消操作。
def show_auto_mode_confirm(live_color_ranges):
    panel_w, panel_h = 500, 360
    panel = np.full((panel_h, panel_w, 3), 240, dtype=np.uint8)
    panel = draw_chinese_text(panel, "請確認以下各顏色之HSV資訊。", (20, 25), font_size=32, color=(0,0,0))
    y = 70
    for color, hsv in live_color_ranges.items():
        ch_color = color
        if color == "Red":
            ch_color = "紅色"
        elif color == "Blue":
            ch_color = "藍色"
        elif color == "Green":
            ch_color = "綠色"
        panel = draw_chinese_text(
            panel,
            f"{ch_color}: [{hsv[0][0]},{hsv[0][1]},{hsv[0][2]}] ~ [{hsv[1][0]},{hsv[1][1]},{hsv[1][2]}]",
            (20, y), font_size=24, color=(0,0,0)
        )
        y += 35
    btns = [
        {"text": "確認", "color": BUTTON_COLOR, "result": True},
        {"text": "取消", "color": BUTTON_COLOR, "result": False},
    ]
    btn_rects = []
    for i, btn in enumerate(btns):
        bx, by, bw, bh = 60 + i*200, panel_h-110, 140, 45
        btn_rects.append((bx, by, bx+bw, by+bh, btn["result"]))
    # 新增紅色提示文字
    panel = draw_chinese_text(panel, "      按下確認後即進入持續辨識的無UI模式!", (20, panel_h-175), font_size=20, color=(255,0,0))
    panel = draw_chinese_text(panel, "      若要關閉則在CMD中按ctrl+c打斷程式", (20, panel_h-150), font_size=20, color=(255,0,0))

    hovered_idx = [None]  # 用list包裝以便內部修改

    def redraw_panel():
        temp_panel = panel.copy()
        for i, btn in enumerate(btns):
            bx, by, bw, bh = 60 + i*200, panel_h-110, 140, 45
            color = btn["color"]
            if hovered_idx[0] == i:
                color = (min(color[0]+80,255), min(color[1]+80,255), min(color[2]+80,255))
            cv2.rectangle(temp_panel, (bx, by), (bx+bw, by+bh), color, -1)
            temp_panel = draw_chinese_text(temp_panel, btn["text"], (bx+20, by+8), font_size=28, color=TEXT_COLOR)
        cv2.imshow("Auto Mode confirm", temp_panel)

    selected = {'result': None}
    def on_mouse(event, x, y, flags, param):
        hover = None
        for i, (bx1, by1, bx2, by2, _) in enumerate(btn_rects):
            if bx1 <= x <= bx2 and by1 <= y <= by2:
                hover = i
                if event == cv2.EVENT_LBUTTONDOWN:
                    selected['result'] = btns[i]["result"]
        if hovered_idx[0] != hover:
            hovered_idx[0] = hover
            redraw_panel()

    cv2.imshow("Auto Mode confirm", panel)
    cv2.setMouseCallback("Auto Mode confirm", on_mouse)
    redraw_panel()
    while True:
        if selected['result'] is not None:
            cv2.destroyWindow("Auto Mode confirm")
            return selected['result']
        evt = cv2.waitKey(10)
        # 新增：檢查視窗是否被手動關閉
        if cv2.getWindowProperty("Auto Mode confirm", cv2.WND_PROP_VISIBLE) < 1:
            print("[MainLocal] Auto Mode confirm window closed by user.")
            return False
        if evt == 27:
            cv2.destroyWindow("Auto Mode confirm")
            return False

# =============================================================================
# Step 8: 鏡頭選擇視窗
# =============================================================================
# `select_camera_dialog` 函式用於讓使用者在多個可用的攝影機之間進行切換。
# 它會：
# 1. 偵測系統上所有可用的攝影機 (索引從 0 到 4)。
# 2. 彈出一個新視窗，將所有可用的攝影機顯示為按鈕。
# 3. 提供一個 "返回" 按鈕，讓使用者可以取消選擇。
# 4. 使用者點擊某個攝影機後，函式會返回該攝影機的索引值。
# 主程式在接收到新的索引值後，會重新初始化攝影機。
def select_camera_dialog():
    available = []
    for idx in range(5):
        cap = cv2.VideoCapture(idx)
        if cap.isOpened():
            available.append(idx)
            cap.release()
    if not available:
        print("未偵測到任何鏡頭")
        return None
    panel_w, panel_h = 400, 80 + 60 * len(available) + 60
    btn_rects = []
    for i, idx in enumerate(available):
        y = 80 + i*50
        btn_x, btn_y, btn_w, btn_h = 40, y, 300, 40
        btn_rects.append((btn_x, btn_y, btn_x+btn_w, btn_y+btn_h, idx))
    # 返回按鈕
    back_btn_y = 80 + len(available)*50 + 10
    back_btn_x, back_btn_w, back_btn_h = 40, 300, 40
    btn_rects.append((back_btn_x, back_btn_y, back_btn_x+back_btn_w, back_btn_y+back_btn_h, "back"))

    hovered_idx = [None]

    def redraw_panel():
        panel = np.full((panel_h, panel_w, 3), 240, dtype=np.uint8)
        panel = draw_chinese_text(panel, "請選擇鏡頭：", (20, 30), font_size=32, color=(0,0,0))
        for i, rect in enumerate(btn_rects):
            bx1, by1, bx2, by2, cam_idx = rect
            color = BUTTON_COLOR
            if i == hovered_idx[0]:
                color = (min(color[0]+80,255), min(color[1]+80,255), min(color[2]+80,255))
            cv2.rectangle(panel, (bx1, by1), (bx2, by2), color, -1)
            if cam_idx == "back":
                text = "返回"
            else:
                text = f"{i+1}. 鏡頭 {cam_idx}"
            panel = draw_chinese_text(panel, text, (bx1+15, by1+5), font_size=28, color=TEXT_COLOR)
        cv2.imshow("Select Camera", panel)

    selected = {'idx': None}
    def on_mouse(event, x, y, flags, param):
        hover = None
        for i, (bx1, by1, bx2, by2, cam_idx) in enumerate(btn_rects):
            if bx1 <= x <= bx2 and by1 <= y <= by2:
                hover = i
                if event == cv2.EVENT_LBUTTONDOWN:
                    selected['idx'] = cam_idx
        if hovered_idx[0] != hover:
            hovered_idx[0] = hover
            redraw_panel()

    redraw_panel()
    cv2.setMouseCallback("Select Camera", on_mouse)
    while True:
        if selected['idx'] is not None:
            cv2.destroyWindow("Select Camera")
            if selected['idx'] == "back":
                return None
            return selected['idx']
        evt = cv2.waitKey(10)
        # 新增：檢查視窗是否被手動關閉
        if cv2.getWindowProperty("Select Camera", cv2.WND_PROP_VISIBLE) < 1:
            print("[MainLocal] Select Camera window closed by user.")
            return None
        if evt == 27 or evt == ord('q'):
            cv2.destroyWindow("Select Camera")
            return None

# --- 新增全域變數 ---
MODE_AUTO = "auto"
MODE_SIM = "sim"
current_mode = MODE_AUTO  # 預設自動辨識
sim_ready_pin = 0         # 模擬模式下的 ready_pin 狀態

# =============================================================================
# Step 9: 主流程 main() - 初始化
# =============================================================================
# `main` 函式是整個程式的進入點和核心邏輯所在。
# 在這個初始階段，它會執行以下操作：
# 1. 宣告會用到的全域變數。
# 2. 使用 `argparse` 解析從命令列傳入的參數 (例如攝影機索引)。
# 3. 呼叫 `initialize_camera` 和 `initialize_arm_controller` 來設定硬體。
# 4. 建立 `StateManager` 物件來管理狀態。
# 5. 從設定檔 `vision_config` 載入預設的顏色範圍，並設定 UI 的初始狀態。
# 6. 建立名為 "ARMCtrl-ALL-IN-ONE" 的主視窗，並將 `on_all_in_one_mouse`
#    設定為其滑鼠事件的回呼函式。
# 7. 初始化計數器 `label_counter` 和其他流程控制變數。
def main():
    global current_color_to_adjust, current_action_from_buttons, live_color_ranges, hsv_values, ui_enabled, save_feedback_end_time, current_mode, sim_ready_pin
    parser = argparse.ArgumentParser(description="ARMCtrl OpenCV Application - Local Display Mode with HSV Adjustment")
    parser = add_common_arguments(parser)
    parser.add_argument('--show_debug_masks', action=argparse.BooleanOptionalAction, default=False, help="Show individual color mask windows for debugging.")
    args = parser.parse_args()
    cap, frame_width, frame_height, fps = initialize_camera(args.camera_index)
    if not cap:
        return
    arm_controller = initialize_arm_controller(args)
    state_manager = StateManager()
    live_color_ranges = deepcopy(vision_config.color_ranges)
    if not live_color_ranges or current_color_to_adjust not in live_color_ranges:
        initial_hsv_for_trackbar = vision_config.DEFAULT_COLOR_RANGES.get(current_color_to_adjust, [[0,0,0],[179,255,255]])
    else:
        initial_hsv_for_trackbar = live_color_ranges[current_color_to_adjust]
    hsv_values = deepcopy(initial_hsv_for_trackbar)
    cv2.namedWindow("ARMCtrl-ALL-IN-ONE")
    cv2.setMouseCallback("ARMCtrl-ALL-IN-ONE", on_all_in_one_mouse)
    print("[MainLocal] System running. Use UI buttons or press 'q' in the OpenCV window to quit.")
    label_counter = Counter()
    window_start_time = None
    window_duration = 3  # 秒
    in_recognition = False

    running = True
    try:
        # =============================================================================
# Step 10: 主迴圈
# =============================================================================
# 程式進入一個 `while running` 的主迴圈，持續處理影像和使用者輸入，直到
# 使用者選擇退出。
# 迴圈的一開始會檢查 `ui_enabled` 變數。
# - 如果 `ui_enabled` 為 `False`，程式會進入無UI (headless) 的自動辨識模式，
#   這個模式下不會顯示任何 UI 視窗，只會在終端機輸出辨識結果和狀態，
#   並直接與機械手臂互動。
# - 如果 `ui_enabled` 為 `True`，程式會繼續執行 UI 互動模式的流程。
        while running:
            # 新增：主視窗被關閉時直接結束
            # if cv2.getWindowProperty("ARMCtrl-ALL-IN-ONE", cv2.WND_PROP_VISIBLE) < 1:
            #     print("[MainLocal] 主視窗被關閉，程式結束。")
            #     break

            # 新增：無UI模式直接跳出主循環或執行無UI流程
            if not ui_enabled:
                # print("[MainLocal] 進入無UI自動辨識模式")
                in_recognition = False
                window_start_time = None
                label_counter.clear()
                while True:
                    ret, frame = cap.read()
                    if not ret:
                        break
                    # 取得 ready_pin 狀態
                    ready_pin_state = 0
                    if hasattr(arm_controller, "get_ready_pin"):
                        ready_pin_state = arm_controller.get_ready_pin()
                    # 狀態機
                    if not in_recognition:
                        if ready_pin_state == 1:
                            in_recognition = True
                            window_start_time = time.time()
                            label_counter.clear()
                            print("[MainLocal] 進入辨識階段")
                        else:
                            time.sleep(0.05)
                            continue
                    else:
                        # 辨識階段
                        live_color_ranges[current_color_to_adjust] = deepcopy(hsv_values)
                        _, labels, _, labels_with_scores = process_frame_and_control_arm(
                            frame, state_manager, None, live_color_ranges,
                            show_debug_windows=False,
                            return_scores=True
                        )
                        if labels_with_scores:
                            top_label, top_score = max(labels_with_scores, key=lambda x: x[1])
                            label_counter[top_label] += 1
                            for label, score in labels_with_scores:
                                if label != top_label and label_counter[label] > 0:
                                    label_counter[label] -= 1
                        now = time.time()
                        if now - window_start_time >= window_duration:
                            if label_counter:
                                most_common_label, count = label_counter.most_common(1)[0]
                                print(f"[MainLocal] 3秒內最多的是 {most_common_label}，計數：{count}，送出對應訊號")
                                if hasattr(arm_controller, f"trigger_action_{most_common_label}"):
                                    getattr(arm_controller, f"trigger_action_{most_common_label}")()
                            in_recognition = False
                            window_start_time = None
                            label_counter.clear()
                break  # 跳出主循環

            ret, frame = cap.read()
            if not ret:
                break

            # --- 立即處理按鈕動作 ---
            # =============================================================================
# Step 11: 按鈕動作處理
# =============================================================================
# 在 UI 模式下，迴圈會檢查 `current_action_from_buttons` 變數是否有值。
# 這個變數由滑鼠回呼函式 `on_all_in_one_mouse` 在偵測到按鈕點擊時設定。
# 根據變數的值，程式會執行相應的動作：
# - "save": 將 `live_color_ranges` 中所有顏色的 HSV 值儲存到設定檔。
# - "set_red", "set_blue", "set_green": 切換 `current_color_to_adjust`，
#   讓 UI 顯示並調整對應顏色的 HSV 值。
# - "quit": 中斷主迴圈，結束程式。
# - "auto_mode": 呼叫 `show_auto_mode_confirm` 視窗，確認後進入無 UI 模式。
# - "select_camera": 呼叫 `select_camera_dialog` 視窗，並在選擇後重新初始化攝影機。
# 處理完畢後，會將 `current_action_from_buttons` 設回 `None`，等待下一次點擊。
            if current_action_from_buttons == "save":
                vision_config.save_color_ranges(live_color_ranges)
                print("[MainLocal] Saved current HSV values for ALL colors to config.")
                save_feedback_end_time = time.time() + 2 # 訊息顯示 2 秒
                current_action_from_buttons = None
            elif current_action_from_buttons == "set_red":
                current_color_to_adjust = "Red"
                hsv_values = deepcopy(live_color_ranges.get("Red", [[0,0,0],[179,255,255]]))
                current_action_from_buttons = None
            elif current_action_from_buttons == "set_blue":
                current_color_to_adjust = "Blue"
                hsv_values = deepcopy(live_color_ranges.get("Blue", [[100,100,100],[120,255,255]]))
                current_action_from_buttons = None
            elif current_action_from_buttons == "set_green":
                current_color_to_adjust = "Green"
                hsv_values = deepcopy(live_color_ranges.get("Green", [[40,100,100],[80,255,255]]))  # 預設綠色範圍
                current_action_from_buttons = None
            elif current_action_from_buttons == "quit":
                print("[MainLocal] Quit button pressed.")
                break
            elif current_action_from_buttons == "auto_mode":
                # 先跳出確認小視窗
                if show_auto_mode_confirm(live_color_ranges):
                    print("[MainLocal] 進入無UI自動辨識模式")
                    ui_enabled = False
                    cv2.destroyAllWindows()
                else:
                    print("[MainLocal] 取消進入無UI自動辨識模式")
                current_action_from_buttons = None
            elif current_action_from_buttons == "select_camera":
                cam_idx = select_camera_dialog()
                if cam_idx is not None:
                    cv2.destroyWindow("ARMCtrl-ALL-IN-ONE")
                    cleanup_resources(cap, arm_controller)
                    cap, frame_width, frame_height, fps = initialize_camera(cam_idx)
                    print(f"[MainLocal] 成功切換到攝影機 {cam_idx}.")
                    arm_controller = initialize_arm_controller(args)
                    state_manager = StateManager()
                    live_color_ranges = deepcopy(vision_config.color_ranges)
                    hsv_values = deepcopy(initial_hsv_for_trackbar)
                    cv2.namedWindow("ARMCtrl-ALL-IN-ONE")
                    cv2.setMouseCallback("ARMCtrl-ALL-IN-ONE", on_all_in_one_mouse)
                    print("[MainLocal] 請重新設定 HSV 範圍.")
                current_action_from_buttons = None

            # --- 模式切換 ---
            key = cv2.waitKey(1) & 0xFF
            if key == ord('a'):
                current_mode = MODE_AUTO
                print("[MainLocal] 切換到一般辨識模式")
                in_recognition = False
                window_start_time = None
                label_counter.clear()
            elif key == ord('s'):
                current_mode = MODE_SIM
                print("[MainLocal] 切換到模擬模式")
                in_recognition = False
                window_start_time = None
                label_counter.clear()
            elif key == ord('d') and current_mode == MODE_SIM:
                sim_ready_pin = 1
                print("[MainLocal] 模擬模式：ready_pin=1（進入辨識階段）")
            elif key == ord('q'):
                break

            # --- 狀態機流程 ---
            # =============================================================================
# Step 12: 狀態機流程 (模式切換與辨識邏輯)
# =============================================================================
# 這部分是程式的核心辨識邏輯，根據 `current_mode` (自動/模擬) 執行不同流程。
#
# **自動模式 (MODE_AUTO):**
# - 此模式下，程式會對每一幀影像進行即時辨識。
# - 呼叫 `process_frame_and_control_arm` 處理影像、辨識顏色、並可能觸發手臂動作。
# - 將結果（原始影像、遮罩）傳給 `draw_combined_ui` 來繪製並更新 UI。
# - 這個模式主要用於即時預覽和調整 HSV，不進行計數和延遲判斷。

            if current_mode == MODE_AUTO:
                # 自動辨識模式：每幀即時辨識，不做計數与統計
                live_color_ranges[current_color_to_adjust] = deepcopy(hsv_values)
                result_frame, labels, masks, labels_with_scores = process_frame_and_control_arm(
                    frame, state_manager, None, live_color_ranges,
                    show_debug_windows=args.show_debug_masks,
                    return_scores=True
                )
                current_mask = None
                if isinstance(masks, dict):
                    current_mask = masks.get(current_color_to_adjust)
                else:
                    current_mask = masks
                # 不顯示計數器
                combined = draw_combined_ui(result_frame, hsv_values, current_color_to_adjust, current_mask, label_counter=None)
                cv2.imshow("ARMCtrl-ALL-IN-ONE", combined)
                if cv2.getWindowProperty("ARMCtrl-ALL-IN-ONE", cv2.WND_PROP_VISIBLE) < 1:
                    print("[MainLocal] 主視窗被關閉，程式結束。")
                    running = False
                    break
            else:
                # 模擬模式
                # 讓 ready_pin_state 同時監測 sim_ready_pin 及真實 ready_pin(內部測試)
                ready_pin_state = sim_ready_pin
                if hasattr(arm_controller, "get_ready_pin"):
                    ready_pin_state = ready_pin_state or arm_controller.get_ready_pin()
                if not in_recognition:
                    if ready_pin_state == 1:
                        in_recognition = True
                        window_start_time = time.time()
                        label_counter.clear()
                        print("[MainLocal] 進入辨識階段")
                    else:
                        standby_frame = frame.copy()
                        standby_frame = draw_chinese_text(standby_frame, "待機中，請等待 ready 訊號", (60, 80), font_size=48, color=(0,0,255))
                        combined = draw_combined_ui(standby_frame, hsv_values, current_color_to_adjust, None, label_counter=None)
                        cv2.imshow("ARMCtrl-ALL-IN-ONE", combined)
                        if cv2.getWindowProperty("ARMCtrl-ALL-IN-ONE", cv2.WND_PROP_VISIBLE) < 1:
                            print("[MainLocal] 主視窗被關閉，程式結束。")
                            running = False
                            break
                        continue
                else:
                    # 辨識階段
                    live_color_ranges[current_color_to_adjust] = deepcopy(hsv_values)
                    result_frame, labels, masks, labels_with_scores = process_frame_and_control_arm(
                        frame, state_manager, None, live_color_ranges,
                        show_debug_windows=args.show_debug_masks,
                        return_scores=True
                    )
                    if labels_with_scores:
                        top_label, top_score = max(labels_with_scores, key=lambda x: x[1])
                        label_counter[top_label] += 1
                        for label, score in labels_with_scores:
                            if label != top_label and label_counter[label] > 0:
                                label_counter[label] -= 1

                    now = time.time()
                    if now - window_start_time >= window_duration:
                        if label_counter:
                            most_common_label, count = label_counter.most_common(1)[0]
                            print(f"[MainLocal] 3秒內最多的是 {most_common_label}，計數：{count}，送出對應訊號")
                            if hasattr(arm_controller, f"trigger_action_{most_common_label}"):
                                getattr(arm_controller, f"trigger_action_{most_common_label}")()
                        # 回到待機階段
                        in_recognition = False
                        window_start_time = None
                        label_counter.clear()
                        sim_ready_pin = 0  # <--- 新增這行，讓 ready_pin 歸零

                    current_mask = None
                    if isinstance(masks, dict):
                        current_mask = masks.get(current_color_to_adjust)
                    else:
                        current_mask = masks
                    combined = draw_combined_ui(result_frame, hsv_values, current_color_to_adjust, current_mask, label_counter=label_counter)
                    cv2.imshow("ARMCtrl-ALL-IN-ONE", combined)
                    # 補上主視窗關閉檢查
                    if cv2.getWindowProperty("ARMCtrl-ALL-IN-ONE", cv2.WND_PROP_VISIBLE) < 1:
                        print("[MainLocal] 主視窗被關閉，程式結束。")
                        running = False
                        break

            # 按鈕動作
            if current_action_from_buttons == "save":
                vision_config.save_color_ranges(live_color_ranges)
                print("[MainLocal] Saved current HSV values for ALL colors to config.")
                save_feedback_end_time = time.time() + 2 # 訊息顯示 2 秒
                current_action_from_buttons = None
            elif current_action_from_buttons == "set_red":
                current_color_to_adjust = "Red"
                hsv_values = deepcopy(live_color_ranges.get("Red", [[0,0,0],[179,255,255]]))
                current_action_from_buttons = None
            elif current_action_from_buttons == "set_blue":
                current_color_to_adjust = "Blue"
                hsv_values = deepcopy(live_color_ranges.get("Blue", [[100,100,100],[120,255,255]]))
                current_action_from_buttons = None
            elif current_action_from_buttons == "set_green":
                current_color_to_adjust = "Green"
                hsv_values = deepcopy(live_color_ranges.get("Green", [[40,100,100],[80,255,255]]))  # 預設綠色範圍
                current_action_from_buttons = None
            elif current_action_from_buttons == "quit":
                print("[MainLocal] Quit button pressed.")
                break
            elif current_action_from_buttons == "auto_mode":
                # 先跳出確認小視窗
                if show_auto_mode_confirm(live_color_ranges):
                    print("[MainLocal] 進入無UI自動辨識模式")
                    ui_enabled = False
                    cv2.destroyAllWindows()
                else:
                    print("[MainLocal] 取消進入無UI自動辨識模式")
                current_action_from_buttons = None
            # 新增鏡頭選擇功能
            elif current_action_from_buttons == "select_camera":
                cam_idx = select_camera_dialog()
                if cam_idx is not None:
                    cv2.destroyWindow("ARMCtrl-ALL-IN-ONE")
                    cleanup_resources(cap, arm_controller)
                    cap, frame_width, frame_height, fps = initialize_camera(cam_idx)
                    print(f"[MainLocal] 成功切換到攝影機 {cam_idx}.")
                    arm_controller = initialize_arm_controller(args)
                    state_manager = StateManager()
                    live_color_ranges = deepcopy(vision_config.color_ranges)
                    hsv_values = deepcopy(initial_hsv_for_trackbar)
                    cv2.namedWindow("ARMCtrl-ALL-IN-ONE")
                    cv2.setMouseCallback("ARMCtrl-ALL-IN-ONE", on_all_in_one_mouse)
                    print("[MainLocal] 請重新設定 HSV 範圍.")
                current_action_from_buttons = None
            if not ui_enabled:
                # 無UI模式下可加自動退出條件或其他自動流程
                pass
    except KeyboardInterrupt:
        print("\n[MainLocal] Program interrupted by user (Ctrl+C).")
    finally:
        # =============================================================================
# Step 13: 程式結束與資源釋放
# =============================================================================
# `try...finally` 結構確保不論程式是正常結束還是因錯誤 (如 `KeyboardInterrupt`)
# 中斷，`finally` 區塊中的程式碼都一定會被執行。
# 這對於釋放硬體資源至關重要，可以避免攝影機或序列埠被鎖定。
# - `cleanup_resources`: 呼叫此函式來安全地釋放攝影機 (`cap.release()`) 和
#   關閉與機械手臂的連線。
# - `cv2.destroyAllWindows()`: 關閉所有由 OpenCV 建立的視窗。
        print("[MainLocal] Cleaning up resources...")
        cleanup_resources(cap, arm_controller)
        cv2.destroyAllWindows()

# =============================================================================
# Step 14: 程式進入點
# =============================================================================
# `if __name__ == "__main__":` 是 Python 的標準寫法。
# 它確保只有當這個腳本是作為主程式直接執行時，`main()` 函式才會被呼叫。
# 如果這個腳本被其他檔案作為模組匯入，`main()` 則不會自動執行。
if __name__ == "__main__":
    main()
