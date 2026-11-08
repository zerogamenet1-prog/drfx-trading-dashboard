# ⚡ DRFX Live Trading Dashboard

ระบบเว็บแดชบอร์ดรายงานผลการเทรดแบบสด (Real-time Live Trading Dashboard) สรุปกำไรรายวัน กราฟการเติบโต และแสดงออเดอร์ที่กำลังถืออยู่แบบ Real-time ตามสไตล์ `dashboard.drfxtrading.net`

---

## 🚀 โครงสร้างระบบ (Architecture)

1. **Dashboard Web Server (`TradingDashboard/server.py`)**
   - รันบน **FastAPI (Python)** เชื่อมต่อข้อมูลสดด้วย **WebSockets**
   - ฐานข้อมูล **SQLite (`dashboard.db`)** บันทึกประวัติ Snapshot และสถิติรายวัน
   - หน้าเว็บ **Dark Mode Fintech UI** (`static/index.html`) พร้อมกราฟ Growth Curve & Daily Bar Chart

2. **MT5 Telemetry Reporter (`DRFX_WebReporter.mq5` / `.ex5`)**
   - อยู่ในโฟลเดอร์ `MQL5\Experts\DRFX_WebReporter.ex5`
   - รวบรวมข้อมูล Balance, Equity, Floating, Today Profit, Yesterday Profit, Max DD และรายการออเดอร์สดทั้งหมด ส่งผ่าน `WebRequest()` ทุก 3 วินาที

---

## 🛠️ วิธีเปิดใช้งาน (Quick Start)

### ขั้นตอนที่ 1: เปิดเซิร์ฟเวอร์ Dashboard
1. ดับเบิ้ลคลิกไฟล์ `start_dashboard.bat` ในโฟลเดอร์ `TradingDashboard`
   *(หรือเปิด Terminal แล้วรัน `python server.py`)*
2. เว็บบราวเซอร์จะเปิดขึ้นมาที่ **`http://localhost:8000`** ทันที
3. คุณสามารถกดปุ่ม **⚡ Load Demo** ด้านบนขวา เพื่อดูตัวอย่างการแสดงผลกราฟและออเดอร์สดได้ทันที!

---

### ขั้นตอนที่ 2: ตั้งค่าใน MT5 ให้ส่งข้อมูลเข้า Dashboard
1. เปิดโปรแกรม **MT5**
2. ไปที่เมนู **Tools -> Options** (หรือกด `Ctrl + O`)
3. เลือกแท็บ **Expert Advisors**
4. ติ๊กถูกที่:
   - ✅ **Allow algorithmic trading**
   - ✅ **Allow WebRequest for listed URL**
5. ดับเบิ้ลคลิกเพิ่ม URL:
   - **`http://localhost:8000`** (หากรันในเครื่องเดียวกัน)
   - *(หากนำเว็บไปขึ้น Cloud VPS ให้ใส่ Domain หรือ IP ของ VPS)*
6. กด **OK**

---

### ขั้นตอนที่ 3: แนบ EA บนกราฟใน MT5
1. ในหน้าต่าง **Navigator** ของ MT5 หาโฟลเดอร์ **Expert Advisors**
2. ลากไฟล์ **`DRFX_WebReporter`** ไปวางบนกราฟใดก็ได้ 1 ใบ
3. ตั้งค่า Input:
   - `InpServerUrl`: `http://localhost:8000/api/report`
   - `InpUpdateIntervalSec`: `3` (ส่งข้อมูลทุก 3 วินาที)
   - `InpAccountCustomName`: ตั้งชื่อพอร์ต เช่น `DRFX-NEMENEXUS (Gold)`
4. กด **OK**
5. ตรวจสอบในแท็บ **Experts** ด้านล่าง จะขึ้นข้อความ:
   `🚀 [DRFX Reporter] Initializing Telemetry Reporter...`
6. ข้อมูลในหน้าเว็บจะอัปเดตแบบสดๆ (Live) ทันที!

---

## 🌟 ฟังก์ชันเด่นในระบบ

* 🔄 **Real-Time WebSockets:** ออเดอร์และกำไรขยับตามกราฟสด ไม่ต้องกดรีเฟรชหน้าเว็บ
* 💱 **Currency Toggle:** สลับดูหน่วยเงินได้ 3 แบบ: **USD ($)**, **CENT (¢)**, และ **THB (฿)** พร้อมเรทแลกเปลี่ยน
* 📊 **Deep View Modal:** คลิกที่การ์ดพอร์ตเพื่อเปิดดูกราฟ:
  - **Equity & Balance Growth Curve:** กราฟวิเคราะห์การเติบโตและการโดนลาก (Drawdown)
  - **14-Day Profit Breakdown:** แท่งเขียววันกำไร แท่งแดงวันขาดทุน
  - **Live Positions Table:** แสดง Ticket, Symbol, Buy/Sell, Lots, Current Price, SL/TP, Floating Profit
* 🧪 **Live Simulation Script:** มีไฟล์ `simulate_live_ticks.py` สำหรับจำลองราคาและออเดอร์ขยับสดโดยไม่ต้องเปิดตลาด

