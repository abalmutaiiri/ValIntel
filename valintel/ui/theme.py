"""Shared visual design constants and Qt stylesheet."""
APP_TITLE = "VALINTEL"

PALETTE = {
    "bg": "#090D14", "sidebar": "#0D1420", "panel": "#121C29",
    "surface": "#182435", "surface2": "#1D2D3D", "line": "#2A3949",
    "text": "#F4F7FB", "muted": "#8B9CB0", "faint": "#617387",
    "red": "#FF4655", "red_dark": "#3C222B", "cyan": "#5AD9CF",
    "green": "#72E4AC", "yellow": "#F9BD74", "blue": "#82B9FF",
}

ROLE = {
    "Astra": "CONTROLLER", "Breach": "INITIATOR", "Brimstone": "CONTROLLER",
    "Chamber": "SENTINEL", "Clove": "CONTROLLER", "Cypher": "SENTINEL",
    "Deadlock": "SENTINEL", "Fade": "INITIATOR", "Gekko": "INITIATOR",
    "Harbor": "CONTROLLER", "Iso": "DUELIST", "Jett": "DUELIST",
    "KAY/O": "INITIATOR", "Killjoy": "SENTINEL", "Miks": "INITIATOR",
    "Neon": "DUELIST", "Omen": "CONTROLLER", "Phoenix": "DUELIST",
    "Raze": "DUELIST", "Reyna": "DUELIST", "Sage": "SENTINEL",
    "Skye": "INITIATOR", "Sova": "INITIATOR", "Tejo": "INITIATOR",
    "Veto": "SENTINEL", "Viper": "CONTROLLER", "Vyse": "SENTINEL",
    "Waylay": "DUELIST", "Yoru": "DUELIST",
}

STYLESHEET = """
* { font-family: 'Segoe UI', 'Inter', sans-serif; }
QWidget { color: #F4F7FB; background: transparent; font-size: 12px; }
QMainWindow, QWidget#Root, QScrollArea#MainScroll, QWidget#MainCanvas { background: #090D14; }
QFrame#Sidebar { background: #0D1420; border-right: 1px solid #263342; }
QFrame#Panel { background: #121C29; border: 1px solid #263647; border-radius: 15px; }
QFrame#Inset { background: #182435; border: 1px solid #27384A; border-radius: 11px; }
QFrame#Feature { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #1C283A, stop:1 #101D2C); border: 1px solid #344253; border-radius: 15px; }
QFrame#HeaderCard { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #242437, stop:0.45 #182637, stop:1 #10232A); border: 1px solid #344354; border-radius: 15px; }
QFrame#Separator { background: #283B4A; max-height: 1px; }
QLabel#Kicker { color: #8DA2B5; font-size: 10px; font-weight: 700; letter-spacing: 2px; }
QLabel#PageTitle { font-size: 27px; font-weight: 800; letter-spacing: 1px; }
QLabel#SectionTitle { font-size: 16px; font-weight: 800; }
QLabel#Muted { color: #8B9CB0; font-size: 12px; }
QLabel#Hint { color: #8095AA; font-size: 11px; }
QLabel#HeroTitle { font-size: 23px; font-weight: 800; letter-spacing: 1px; }
QLabel#BigName { font-size: 22px; font-weight: 800; }
QLabel#StatValue { font-size: 15px; font-weight: 800; }
QLabel#Pill { color: #80E5BA; background: #173A35; border: 1px solid #255B50; border-radius: 12px; padding: 5px 10px; font-size: 10px; font-weight: 800; }
QLabel#AlertPill { color: #F7BB76; background: #422E26; border: 1px solid #604632; border-radius: 12px; padding: 5px 10px; font-size: 10px; font-weight: 800; }
QPushButton { background: #1B2B3B; border: 1px solid #344657; color: #F0F4FA; border-radius: 9px; padding: 9px 15px; font-weight: 700; }
QPushButton:hover { background: #283B4C; border: 1px solid #536579; }
QPushButton:pressed { background: #14212D; }
QPushButton:disabled { color: #63778A; background: #17212D; border: 1px solid #263444; }
QPushButton#Primary { background: #FF4655; color: white; border: 1px solid #FF6873; }
QPushButton#Primary:hover { background: #FF6070; }
QPushButton#Primary:disabled { background: #523039; color: #B18E94; border: 1px solid #603C46; }
QPushButton#Teal { background: #1B4242; color: #71E7D2; border: 1px solid #2B7A75; }
QPushButton#Teal:hover { background: #285751; }
QPushButton#Nav { text-align: left; background: transparent; border: 1px solid transparent; padding: 12px 14px; color: #8B9CB0; font-weight: 600; }
QPushButton#Nav:hover { background: #1A2938; color: #F4F7FB; }
QPushButton#NavActive { text-align: left; background: #202D40; border: 1px solid #334758; border-left: 3px solid #FF4655; padding: 12px 14px; color: white; font-weight: 800; }
QLineEdit, QComboBox { background: #101A27; border: 1px solid #324458; border-radius: 9px; padding: 10px 12px; selection-background-color: #FF4655; color: white; }
QLineEdit:focus, QComboBox:focus { border: 1px solid #5AD9CF; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: #162433; color: white; border: 1px solid #344657; selection-background-color: #31485C; }
QCheckBox { color: #D5E0EA; spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #607082; border-radius: 4px; background: #0D1723; }
QCheckBox::indicator:checked { background: #FF4655; border: 1px solid #FF4655; image: none; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: #111A27; width: 8px; margin: 2px; border-radius: 4px; }
QScrollBar::handle:vertical { background: #3D5063; border-radius: 4px; min-height: 32px; }
QScrollBar:horizontal { background: #111A27; height: 8px; margin: 2px; border-radius: 4px; }
QScrollBar::handle:horizontal { background: #3D5063; border-radius: 4px; min-width: 32px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0px; width: 0px; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }
QProgressBar { background: #253344; border: none; border-radius: 4px; height: 8px; text-align: center; }
QProgressBar::chunk { background: #FF4655; border-radius: 4px; }
QDialog { background: #111B28; }
"""
