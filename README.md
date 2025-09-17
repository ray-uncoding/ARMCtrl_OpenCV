# ARMCtrl_OpenCV

基於 OpenCV 的機械手臂視覺控制系統，支援 HSV 顏色調整、形狀辨識、GPIO 控制等功能。

---

## 樹莓派快速啟動

```bash
cd Desktop
git clone https://github.com/ray-uncoding/ARMCtrl_OpenCV.git
cd ARMCtrl_OpenCV
pip install -r requirements.txt --break-system-packages
python main_local.py
```

---

## 程式功能

- **即時影像辨識**：紅/藍/綠色物件的方形/三角形辨識
- **HSV 調整介面**：滑鼠拖曳調整顏色範圍
- **GPIO 控制**：透過繼電器控制外部設備
- **自動辨識模式**：3秒計時辨識並觸發動作

---

## 程式碼結構

```text
ARMCtrl_OpenCV/
├── main_local.py              # 主程式 - 互動式視覺調整界面
├── camera_test.py             # 攝影機測試工具
├── requirements.txt           # 套件需求
├── chinese.ttf               # 中文字型檔
└── utils/                    # 核心模組
    ├── app_core.py           # 應用程式核心功能
    ├── arm_controller/       # 硬體控制
    │   └── pi_gpio_controller.py  # 樹莓派 GPIO 控制
    └── vision_processing/    # 視覺處理
        ├── detector.py       # 物件偵測核心
        ├── config.py        # 設定管理
        ├── color_config.json # HSV 顏色配置
        ├── ui_basic.py      # UI 繪製工具
        ├── state_manager.py # 狀態管理
        ├── confidence_scorer.py # 信心度計算
        └── feature_validator.py # 特徵驗證
```

### 主要檔案說明

- **main_local.py**: 主要使用的程式，提供完整的 HSV 調整 UI 和即時辨識功能
- **utils/detector.py**: 物件偵測邏輯，包含顏色過濾和形狀辨識
- **utils/pi_gpio_controller.py**: 樹莓派 GPIO 控制，透過繼電器觸發外部設備
- **color_config.json**: 儲存 HSV 顏色範圍設定，可透過 UI 調整並保存

### GPIO 控制協議

系統使用 5 個 GPIO 腳位控制外部設備：

- **Ready Pin (GPIO 26)**: 監聽外部設備的啟動信號，觸發整個辨識流程
- **Relay 1 (GPIO 17)**: 觸發信號，告知外部設備開始執行動作
- **Relay 2-4 (GPIO 27,22,23)**: 3-bit 數據編碼，指定要執行的動作類型

**工作流程：**
1. 外部設備透過 GPIO 26 發送準備信號
2. 系統進行 3 秒物件辨識
3. 透過 Relay 1 發送觸發信號
4. 透過 Relay 2-4 的編碼組合告知動作類型（支援 6 種物件組合）

---

## 使用說明

1. 啟動程式後會開啟攝影機視窗
2. 使用右側按鈕切換要調整的顏色（紅/藍/綠）
3. 拖曳 HSV 滑桿調整顏色範圍
4. 點擊「儲存」保存設定
5. 點擊「自動模式」進入辨識模式

---

## 注意事項

- 需要 USB 攝影機或樹莓派攝影機模組
- 樹莓派需要連接 4 路繼電器模組（GPIO 17,27,22,23）
- 外部設備透過 GPIO 26 觸發辨識流程
- 中文字型檔案 `chinese.ttf` 需放在專案根目錄
