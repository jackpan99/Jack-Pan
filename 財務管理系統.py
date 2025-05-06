import sys, os
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import signal
import logging
from typing import Dict, Optional, Tuple
from kivy.app import App
from kivy.config import Config
from kivy.core.text import LabelBase
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.popup import Popup
from kivy.uix.spinner import Spinner
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.uix.screenmanager import Screen
from kivy.graphics import Color, RoundedRectangle
import matplotlib.pyplot as plt
from sklearn.ensemble import RandomForestRegressor
import re  # 添加這一行

# 設定預設視窗大小（根據圖片尺寸調整）
#Window.size = (750, 850)  # 預設寬度 720px，高度 1280px，根據您的需求調整
window_size = (750, 850)  # Define a default window size
Window.size = window_size

# 獲取螢幕尺寸並將視窗置於正中央
#screen_width, screen_height = Window.system_size  # 獲取螢幕寬度和高度
#window_width, window_height = window_size
#Window.left = (screen_width - window_width) / 2  # 計算水平居中位置
#Window.top = (screen_height - window_height) / 2  # 計算垂直居中位置

# Logging setup
logging.basicConfig(filename='finance_app.log', level=logging.DEBUG,
                   format='%(asctime)s - %(levelname)s - %(message)s')

# Configuration
os.environ['KIVY_CLOCK'] = 'interrupt'
Config.set('graphics', 'width', '1000')
Config.set('graphics', 'height', '700')
Config.set('input', 'mouse', 'mouse,multitouch_on_demand')

# Font registration
try:
    font_path = os.path.join(sys._MEIPASS if getattr(sys, 'frozen', False) else os.path.dirname(__file__),
                            "fonts", "NotoSansTC-Regular.ttf")
    LabelBase.register("CustomFont", font_path)
except Exception as e:
    logging.error(f"Failed to load font: {e}")
    LabelBase.register("CustomFont", "Microsoft JhengHei")  # 備用字體
#plt.rcParams['font.sans-serif'] = ['Noto Sans TC', 'Microsoft JhengHei', 'Arial Unicode MS']
#plt.rcParams['axes.unicode_minus'] = False

# Categories
INCOME_CATEGORIES = ['薪資', '獎金', '投資', '其他收入']
EXPENSE_CATEGORIES = ['飲食', '交通', '娛樂', '購物', '房租', '水電費', '其他支出']

# Theme settings
THEMES = {
    'light': {
        'background': (0.96, 0.98, 1, 1),
        'card': (1, 1, 1, 1),
        'text': (0.2, 0.2, 0.2, 1),
        'accent': (0.2, 0.6, 1, 1),
        'error': (0.9, 0.3, 0.3, 1)
    },
    'dark': {
        'background': (0.1, 0.1, 0.1, 1),
        'card': (0.2, 0.2, 0.2, 1),
        'text': (0.9, 0.9, 0.9, 1),
        'accent': (0.4, 0.7, 1, 1),
        'error': (1, 0.4, 0.4, 1)
    }
}

try:
    from kivy_garden.matplotlib.backend_kivyagg import FigureCanvasKivyAgg
except ImportError:
    FigureCanvasKivyAgg = None

class JsonFileHandler:
    def __init__(self, filename: str):
        self.filename = filename
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        if not os.path.exists(self.filename):
            with open(self.filename, 'w', encoding='utf-8') as f:
                json.dump([], f, ensure_ascii=False)

    def read(self):
        try:
            with open(self.filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Error reading {self.filename}: {e}")
            return []

    def write(self, data):
        try:
            with open(self.filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            return True
        except Exception as e:
            logging.error(f"Error writing to {self.filename}: {e}")
            return False

    def backup(self):
        backup_file = f"{self.filename}.backup"
        try:
            with open(self.filename, 'r', encoding='utf-8') as src, open(backup_file, 'w', encoding='utf-8') as dst:
                dst.write(src.read())
            logging.info(f"Backup created: {backup_file}")
            return True
        except Exception as e:
            logging.error(f"Backup failed: {e}")
            return False

class FinanceData:
    def __init__(self, filename="transactions.csv"):
        self.filename = filename  # 修正：添加 filename 屬性
        self.df = pd.DataFrame(columns=['date', 'type', 'category', 'amount', 'notes'])
        self.budgets = {}
        self.load()

    def load(self):
        if os.path.exists(self.filename):
            df = pd.read_csv(self.filename, encoding='utf-8')  # 明確指定編碼
            # 確保 'notes' 欄存在並轉換為字符串，缺失值填為空字符串
            if 'notes' in df.columns:
                df['notes'] = df['notes'].fillna('').astype(str)
            else:
                df['notes'] = ''
            for index, row in df.iterrows():
                try:
                    # 驗證日期格式
                    if pd.isna(row['date']) or not isinstance(row['date'], str) or not re.match(r'^\d{4}-\d{2}-\d{2}$', row['date']):
                        logging.warning(f"[Skipping invalid transaction] 'date' at index {index}: {row['date']}")
                        continue
                    datetime.strptime(row['date'], '%Y-%m-%d')
                    self.df = pd.concat([self.df, pd.DataFrame([row])], ignore_index=True)
                except ValueError as e:
                    logging.warning(f"[Skipping invalid transaction] 'date' at index {index}: {row['date']} - {e}")
        else:
            self.df.to_csv(self.filename, index=False)
            logging.info(f"Created new transactions file: {self.filename}")

    def add_transaction(self, t_type: str, category: str, amount: float, note: str, date: datetime = None) -> bool:
        if date is None:
            date = datetime.now()
        if amount <= 0 or not category:
            logging.warning(f"Invalid transaction: amount={amount}, category={category}")
            return False
        transaction = pd.DataFrame({
            'date': [date.strftime('%Y-%m-%d')],
            'type': [t_type],
            'category': [category],
            'amount': [amount],
            'notes': [note]
        })
        self.df = pd.concat([self.df, transaction], ignore_index=True)
        self.df.to_csv(self.filename, index=False)
        logging.info(f"Added transaction: {date}, {t_type}, {category}, {amount}")
        return True

    def update_transaction(self, index: int, t_type: str, category: str, amount: float, note: str, date: datetime) -> bool:
        if amount <= 0 or not category:
            logging.warning(f"Invalid update: amount={amount}, category={category}")
            return False
        if index < len(self.df):
            self.df.at[index, 'date'] = date.strftime('%Y-%m-%d')
            self.df.at[index, 'type'] = t_type
            self.df.at[index, 'category'] = category
            self.df.at[index, 'amount'] = amount
            self.df.at[index, 'notes'] = note
            self.df.to_csv(self.filename, index=False)
            logging.info(f"Transaction updated: index={index}")
            return True
        return False

    def delete_transaction(self, index: int) -> bool:
        if index < len(self.df):
            # 備份當前數據
            backup_filename = f"transactions_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            self.df.to_csv(backup_filename, index=False)
            logging.info(f"Backup created: {backup_filename}")
            # 刪除交易
            self.df = self.df.drop(index).reset_index(drop=True)
            self.df.to_csv(self.filename, index=False)
            logging.info(f"Transaction deleted: index={index}")
            return True
        return False

    def get_transactions(self, start_date: datetime = None, end_date: datetime = None) -> pd.DataFrame:
        df = self.df.copy()
        df['date'] = pd.to_datetime(df['date'])
        if start_date:
            df = df[df['date'] >= start_date]
        if end_date:
            df = df[df['date'] <= end_date]
        return df.sort_values('date')

    def get_cash_flow(self) -> Dict[str, pd.Series]:
        monthly_data = self.get_transactions(datetime(2025, 5, 1), datetime(2025, 5, 31))
        income = monthly_data[monthly_data['type'] == '收入'].groupby(monthly_data['date'].dt.strftime('%Y-%m'))['amount'].sum()
        expense = monthly_data[monthly_data['type'] == '支出'].groupby(monthly_data['date'].dt.strftime('%Y-%m'))['amount'].sum()
        return {'income': income, 'expense': expense}

    def get_budget_comparison(self) -> Dict[str, Dict[str, float]]:
        now = datetime.now()
        start_date = datetime(now.year, now.month, 1)
        end_date = datetime(now.year + 1, 1, 1) if now.month == 12 else datetime(now.year, now.month + 1, 1)
        end_date -= timedelta(days=1)
        monthly_expenses = self.get_transactions(start_date, end_date)
        monthly_expenses = monthly_expenses[monthly_expenses['type'] == '支出']
        logging.info(f"Monthly Expenses: {monthly_expenses.to_dict()}")
        category_expenses = monthly_expenses.groupby('category')['amount'].sum().to_dict()
        logging.info(f"Category Expenses: {category_expenses}")
        comparison = {}
        all_categories = set(self.budgets.keys()).union(set(category_expenses.keys()))
        for category in all_categories:
            budget = self.budgets.get(category, 0)
            actual = category_expenses.get(category, 0)
            remaining = budget - actual if budget > 0 else 0
            percentage = (actual / budget * 100) if budget > 0 else 0
            comparison[category] = {
                'budget': budget,
                'actual': actual,
                'remaining': remaining,
                'percentage': percentage
            }
        return comparison

    def update_budget(self, category: str, amount: float) -> bool:
        if amount < 0:
            return False
        self.budgets[category] = amount
        logging.info(f"Budget updated: {category}, {amount}")
        return True

    def export_to_csv(self, filename: str) -> bool:
        try:
            self.df.to_csv(filename, index=False, encoding='utf-8-sig')
            logging.info(f"Data exported to {filename}")
            return True
        except Exception as e:
            logging.error(f"Export failed: {e}")
            return False

class BudgetAdvisor:
    def __init__(self, data: FinanceData):
        self.data = data
        self.model = RandomForestRegressor(n_estimators=50, random_state=42)
        self.trained = False
        self.train_model()

    def train_model(self) -> bool:
        features, targets = self._extract_features_targets()
        if features is not None and len(features) >= 5:
            try:
                self.model.fit(features, targets)
                self.trained = True
                logging.info("Model trained successfully")
                return True
            except Exception as e:
                logging.error(f"Model training failed: {e}")
                return False
        return False

    def _extract_features_targets(self) -> Tuple[Optional[pd.DataFrame], Optional[pd.Series]]:
        df = self.data.df.copy()
        df['date'] = pd.to_datetime(df['date'])
        if df.empty or len(df) < 5:
            return None, None
        df['Year'] = df['date'].dt.year
        df['Month'] = df['date'].dt.month
        grouped = df.groupby(['Year', 'Month', 'type'])['amount'].sum().unstack(fill_value=0)
        if '收入' not in grouped.columns or '支出' not in grouped.columns:
            return None, None
        features = grouped[['收入', '支出']].reset_index()
        features['MonthOfYear'] = features['Month']
        features['TimeIndex'] = features['Year'] * 12 + features['Month']
        for i in range(1, 3):
            for col in ['收入', '支出']:
                features[f'{col}_lag{i}'] = features[col].shift(i).fillna(0)
        features['IncomeTrend'] = features['收入'].pct_change().fillna(0)
        features['ExpenseTrend'] = features['支出'].pct_change().fillna(0)
        features = features.iloc[2:].copy()
        features['Savings'] = features['收入'] - features['支出']
        features['SavingsRate'] = features.apply(lambda x: x['Savings'] / x['收入'] if x['收入'] > 0 else 0, axis=1)
        X = features.drop(['Year', 'Month', 'Savings', 'SavingsRate'], axis=1)
        y = features['SavingsRate']
        return X, y

    def get_recommendation(self, current_income: float, current_expense: float) -> str:
        if not self.trained:
            return "請記錄至少5個月的財務資料以獲得建議。"
        now = datetime.now()
        year, month = now.year, now.month
        time_index = year * 12 + month
        cash_flow = self.data.get_cash_flow()
        recent_income = cash_flow['income'].tail(3).mean() if not cash_flow['income'].empty else 0
        recent_expense = cash_flow['expense'].tail(3).mean() if not cash_flow['expense'].empty else 0
        X_pred = pd.DataFrame({
            '收入': [current_income], '支出': [current_expense], 'MonthOfYear': [month],
            'TimeIndex': [time_index], '收入_lag1': [recent_income], '支出_lag1': [recent_expense],
            '收入_lag2': [recent_income], '支出_lag2': [recent_expense],
            'IncomeTrend': [0], 'ExpenseTrend': [0]
        })
        try:
            predicted_savings_rate = self.model.predict(X_pred)[0]
            expected_savings = current_income * predicted_savings_rate
            if predicted_savings_rate > 0.2:
                return f"本月預計儲蓄 {expected_savings:,.0f} 元 (儲蓄率 {predicted_savings_rate*100:.1f}%)，保持良好財務習慣！"
            elif predicted_savings_rate > 0:
                return f"本月預計儲蓄 {expected_savings:,.0f} 元 (儲蓄率 {predicted_savings_rate*100:.1f}%)，可減少非必要支出。"
            else:
                return f"本月可能超支 {abs(expected_savings):,.0f} 元，建議控制支出。"
        except Exception as e:
            logging.error(f"Recommendation failed: {e}")
            return "無法生成建議，請檢查資料完整性。"
        
class CLabel(Label):
    def __init__(self, **kwargs):
        kwargs.setdefault('font_name', 'CustomFont')
        kwargs.setdefault('color', THEMES['light']['text'])
        super().__init__(**kwargs)

class CButton(Button):
    def __init__(self, **kwargs):
        kwargs.setdefault('font_name', 'CustomFont')
        kwargs.setdefault('background_color', THEMES['light']['accent'])
        super().__init__(**kwargs)
        self.bind(on_enter=self._on_enter, on_leave=self._on_leave)

    def _on_enter(self, *args):
        self.background_color = [x * 0.9 for x in self.background_color[:3]] + [1]

    def _on_leave(self, *args):
        self.background_color = THEMES['light']['accent']

class CTextInput(TextInput):
    def __init__(self, **kwargs):
        kwargs.setdefault('font_name', 'CustomFont')
        kwargs.setdefault('background_color', (0.98, 0.98, 0.98, 1))
        super().__init__(**kwargs)

class CSpinner(Spinner):
    def __init__(self, **kwargs):
        kwargs.setdefault('font_name', 'CustomFont')
        kwargs.setdefault('background_color', (0.9, 0.9, 1, 1))
        super().__init__(**kwargs)

class RoundedButton(Button):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.background_normal = ''
        self.background_color = (0, 0, 0, 0)
        with self.canvas.before:
            Color(*THEMES['light']['accent'])
            self.rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(12)])
        self.bind(pos=self.update_rect, size=self.update_rect)
        self.bind(on_enter=self._on_enter, on_leave=self._on_leave)

    def update_rect(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size

    def _on_enter(self, *args):
        with self.canvas.before:
            Color(*[x * 0.9 for x in THEMES['light']['accent'][:3]], 1)
            self.rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(12)])

    def _on_leave(self, *args):
        with self.canvas.before:
            Color(*THEMES['light']['accent'])
            self.rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(12)])

class Card(BoxLayout):
    def __init__(self, bg_color=THEMES['light']['card'], **kwargs):
        super().__init__(**kwargs)
        self.bg_color = bg_color  # 修正：添加 bg_color 屬性
        with self.canvas.before:
            Color(0, 0, 0, 0.1)
            self.shadow = RoundedRectangle(pos=(self.x+dp(2), self.y-dp(4)), size=self.size, radius=[dp(16)])
            Color(*self.bg_color)
            self.rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(16)])
        self.bind(pos=self.update_rect, size=self.update_rect)
        logging.info(f"Card initialized with bg_color {self.bg_color}")

    def update_rect(self, *args):
        self.shadow.pos = (self.x+dp(2), self.y-dp(4))
        self.shadow.size = self.size
        self.rect.pos = self.pos
        self.rect.size = self.size

    def update_color(self, theme):
        self.bg_color = THEMES[theme]['card']
        self.canvas.before.clear()
        with self.canvas.before:
            Color(0, 0, 0, 0.1)
            self.shadow = RoundedRectangle(pos=(self.x + dp(2), self.y - dp(4)), size=self.size, radius=[dp(16)])
            Color(*self.bg_color)
            self.rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(16)])
        logging.info(f"Card color updated to {self.bg_color}")

class TransactionItem(BoxLayout):
    def __init__(self, index, date, t_type, category, amount, note, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'horizontal'
        self.size_hint_y = None
        self.height = dp(40)
        self.padding = [dp(5), dp(5)]
        with self.canvas.before:
            Color(0.95, 0.95, 0.98, 1) if index % 2 == 0 else Color(1, 1, 1, 1)
            self.rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(8)])
        self.bind(pos=self._update_rect, size=self._update_rect)
        date_str = date.strftime('%Y-%m-%d') if isinstance(date, datetime) else str(date)
        self.add_widget(CLabel(text=date_str, font_size=sp(16), size_hint_x=0.15))
        color = (0, 0.7, 0, 1) if t_type == '收入' else (0.8, 0, 0, 1)
        self.add_widget(CLabel(text=t_type, font_size=sp(16), size_hint_x=0.1, color=color))
        self.add_widget(CLabel(text=category, font_size=sp(16), size_hint_x=0.15))
        self.add_widget(CLabel(text=f"{amount:,.0f}", font_size=sp(16), size_hint_x=0.15, color=color))
        # 確保 note 是字符串
        note_str = str(note) if note is not None else ''
        self.add_widget(CLabel(text=note_str, font_size=sp(16), size_hint_x=0.3))
        btns = BoxLayout(orientation='horizontal', size_hint_x=0.15, spacing=dp(5))
        self.edit_button = RoundedButton(text="編輯", size_hint=(None, 0.8), width=dp(50))
        self.delete_button = RoundedButton(text="刪除", size_hint=(None, 0.8), width=dp(50), background_color=THEMES['light']['error'])
        btns.add_widget(self.edit_button)
        btns.add_widget(self.delete_button)
        self.add_widget(btns)

    def _update_rect(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size

class HomeScreen(Screen):
    def __init__(self, finance_data, budget_advisor, **kwargs):
        super().__init__(**kwargs)
        self.finance_data = finance_data
        self.budget_advisor = budget_advisor
        self.theme = 'light'
        self.layout = BoxLayout(orientation='vertical', padding=dp(15), spacing=dp(10))
        
        # Title
        title_card = Card(bg_color=THEMES[self.theme]['card'], orientation='vertical', size_hint_y=0.12, padding=dp(10))
        title_row = BoxLayout(orientation='horizontal')
        title_row.add_widget(CLabel(text="個人財務管理系統", font_size=dp(26), bold=True, color=THEMES[self.theme]['accent'], size_hint_x=0.7))
        title_row.add_widget(CLabel(text=datetime.now().strftime("%Y年%m月%d日"), font_size=dp(16), size_hint_x=0.3, halign='right'))
        title_card.add_widget(title_row)
        title_card.add_widget(CLabel(text="版權所有 by Jack Pan 2025.05.02", font_size=dp(12), color=(0.5,0.5,0.5,1)))
        self.layout.add_widget(title_card)

        # Summary
        self.summary_layout = BoxLayout(orientation='horizontal', size_hint_y=0.13, spacing=dp(10))
        self.summary_layout.add_widget(self._create_summary_card("本月收入", "income"))
        self.summary_layout.add_widget(self._create_summary_card("本月支出", "expense"))
        self.summary_layout.add_widget(self._create_summary_card("本月結餘", "balance"))
        self.layout.add_widget(self.summary_layout)

        # Add Transaction
        # 在 HomeScreen 的 __init__ 方法中，找到 Add Transaction 部分的程式碼並調整
        add_card = Card(bg_color=THEMES[self.theme]['card'], orientation='vertical', size_hint_y=0.20, padding=dp(12), spacing=dp(8))  # 從 0.25 減小到 0.20
        add_card.add_widget(CLabel(text="快速新增交易", font_size=dp(16), size_hint_y=0.2))
        form_layout = GridLayout(cols=4, spacing=dp(15), padding=[dp(10), dp(5)], size_hint_y=0.65)
        self.type_spinner = CSpinner(text='收入', values=('收入', '支出'), size_hint_x=0.25, font_size=sp(16), height=dp(30))  # 減小字體並指定高度
        self.category_spinner = CSpinner(text='類別', values=INCOME_CATEGORIES, size_hint_x=0.25, font_size=sp(16), height=dp(30))
        self.amount_input = CTextInput(hint_text='金額', input_filter='float', multiline=False, size_hint_x=0.2, font_size=sp(16), height=dp(30))
        self.note_input = CTextInput(hint_text='備註', multiline=False, size_hint_x=0.3, font_size=sp(16), height=dp(30))  # 減小字體並指定高度
        self.type_spinner.bind(text=self._update_categories)
        form_layout.add_widget(self.type_spinner)
        form_layout.add_widget(self.category_spinner)
        form_layout.add_widget(self.amount_input)
        form_layout.add_widget(self.note_input)
        add_card.add_widget(form_layout)
        add_btn = RoundedButton(text='新增交易', size_hint=(1, None), height=dp(36))
        add_btn.bind(on_press=self._add_transaction)
        add_card.add_widget(add_btn)
        self.layout.add_widget(add_card)

        # Advice
        advice_card = Card(bg_color=THEMES[self.theme]['card'], orientation='vertical', size_hint_y=0.10, padding=dp(10))  # 從 0.12 減小到 0.10
        advice_card.add_widget(CLabel(text="智能財務建議", font_size=dp(16), size_hint_y=0.2))
        self.advice_content = CLabel(text="開始記錄收支以獲取建議", halign='center', valign='top', size_hint_y=0.8, font_size=sp(12), text_size=(800, None))
        advice_card.add_widget(self.advice_content)
        self.layout.add_widget(advice_card)

        # Recent Transactions
        self.layout.add_widget(CLabel(text="最近交易記錄", font_size=dp(18), size_hint_y=0.05))
        self.scroll_view = ScrollView(size_hint_y=0.42, do_scroll_y=True)  # 從 0.35 增加到 0.42
        self.recent_transactions_layout = GridLayout(cols=1, spacing=dp(5), size_hint_y=None)
        self.recent_transactions_layout.bind(minimum_height=self.recent_transactions_layout.setter('height'))
        self.scroll_view.add_widget(self.recent_transactions_layout)
        self.layout.add_widget(self.scroll_view)

        # Exit
        exit_btn = RoundedButton(text="離開程式", size_hint=(1, 0.05), background_color=THEMES[self.theme]['error'])
        exit_btn.bind(on_press=self._exit_app)
        self.layout.add_widget(exit_btn)
        self.add_widget(self.layout)
        self._update_categories(None, '收入')
        Clock.schedule_once(self._update_summary, 0)
        Clock.schedule_once(self._update_advice, 0)
        Clock.schedule_once(self._load_recent_transactions, 0)

    def _create_summary_card(self, title, card_type):
        card = Card(bg_color=THEMES[self.theme]['card'], orientation='vertical', padding=dp(15), spacing=dp(5))
        title_label = CLabel(text=title, font_size=dp(16), size_hint_y=0.3)
        amount_label = CLabel(text="0", font_size=dp(24), bold=True, size_hint_y=0.5)
        if card_type == "income":
            amount_label.color = (0, 0.7, 0, 1)
        elif card_type == "expense":
            amount_label.color = (0.8, 0, 0, 1)
        else:
            amount_label.color = (0, 0, 0.8, 1)
        card.amount_label = amount_label
        card.add_widget(title_label)
        card.add_widget(amount_label)
        return card

    def _update_categories(self, spinner, text):
        self.category_spinner.values = INCOME_CATEGORIES if text == '收入' else EXPENSE_CATEGORIES
        self.category_spinner.text = self.category_spinner.values[0]

    def _add_transaction(self, instance):
        try:
            t_type = self.type_spinner.text
            category = self.category_spinner.text
            amount = float(self.amount_input.text) if self.amount_input.text else 0
            note = self.note_input.text
            if amount <= 0 or category == '類別':
                Popup(title='錯誤', content=CLabel(text='請輸入有效金額和類別'), size_hint=(0.4, 0.2)).open()
                return
            success = self.finance_data.add_transaction(t_type, category, amount, note)
            if success:
                self.amount_input.text = ''
                self.note_input.text = ''
                self._update_summary()
                self._update_advice()
                self._load_recent_transactions()
                popup = Popup(title='成功', content=CLabel(text='交易已新增'), size_hint=(0.4, 0.2))
                popup.open()
                Clock.schedule_once(popup.dismiss, 1)
            else:
                Popup(title='錯誤', content=CLabel(text='新增失敗'), size_hint=(0.4, 0.2)).open()
        except Exception as e:
            logging.error(f"Add transaction failed: {e}")
            Popup(title='錯誤', content=CLabel(text=f'錯誤: {str(e)}'), size_hint=(0.4, 0.2)).open()

    def _update_summary(self, dt=None):
        now = datetime.now()
        start_date = datetime(now.year, now.month, 1)
        end_date = datetime(now.year + 1, 1, 1) if now.month == 12 else datetime(now.year, now.month + 1, 1)
        end_date -= timedelta(days=1)
        monthly_data = self.finance_data.get_transactions(start_date, end_date)
        income = monthly_data[monthly_data['type'] == '收入']['amount'].sum() if not monthly_data.empty else 0
        expense = monthly_data[monthly_data['type'] == '支出']['amount'].sum() if not monthly_data.empty else 0
        balance = income - expense
        for child in self.summary_layout.children:
            if hasattr(child, 'amount_label'):
                label = child.amount_label
                if '收入' in child.children[1].text:
                    label.text = f"{income:,.0f} 元"
                elif '支出' in child.children[1].text:
                    label.text = f"{expense:,.0f} 元"
                else:
                    label.text = f"{balance:,.0f} 元"

    def _update_advice(self, dt=None):
        now = datetime.now()
        start_date = datetime(now.year, now.month, 1)
        end_date = datetime(now.year + 1, 1, 1) if now.month == 12 else datetime(now.year, now.month + 1, 1)
        end_date -= timedelta(days=1)
        monthly_data = self.finance_data.get_transactions(start_date, end_date)
        income = monthly_data[monthly_data['type'] == '收入']['amount'].sum() if not monthly_data.empty else 0
        expense = monthly_data[monthly_data['type'] == '支出']['amount'].sum() if not monthly_data.empty else 0
        self.advice_content.text = self.budget_advisor.get_recommendation(income, expense)

    def _load_recent_transactions(self, dt=None):
        self.recent_transactions_layout.clear_widgets()
        transactions = self.finance_data.get_transactions().tail(15)
        if transactions.empty:
            self.recent_transactions_layout.add_widget(CLabel(text="尚無交易記錄", font_size=dp(14), height=dp(40)))
        else:
            for i, (idx, row) in enumerate(transactions.iterrows()):
                item = TransactionItem(i, row['date'], row['type'], row['category'], row['amount'], row['notes'])
                item.edit_button.bind(on_press=lambda btn, index=idx: self._edit_transaction(index))
                item.delete_button.bind(on_press=lambda btn, index=idx: self._delete_transaction(index))
                self.recent_transactions_layout.add_widget(item)
        Clock.schedule_once(lambda dt: setattr(self.scroll_view, 'scroll_y', 0), 0.1)

    def _edit_transaction(self, index):
        row = self.finance_data.df.loc[index]
        content = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(10))
        type_layout = BoxLayout(size_hint_y=0.15)
        type_layout.add_widget(CLabel(text='交易類型:', size_hint_x=0.3))
        type_spinner = CSpinner(text=row['type'], values=('收入', '支出'), size_hint_x=0.7)
        type_layout.add_widget(type_spinner)
        content.add_widget(type_layout)
        category_layout = BoxLayout(size_hint_y=0.15)
        category_layout.add_widget(CLabel(text='交易類別:', size_hint_x=0.3))
        category_spinner = CSpinner(text=row['category'], values=INCOME_CATEGORIES if row['type'] == '收入' else EXPENSE_CATEGORIES, size_hint_x=0.7)
        category_layout.add_widget(category_spinner)
        content.add_widget(category_layout)
        amount_layout = BoxLayout(size_hint_y=0.15)
        amount_layout.add_widget(CLabel(text='金額:', size_hint_x=0.3))
        amount_input = CTextInput(text=str(row['amount']), input_filter='float', multiline=False, size_hint_x=0.7)
        amount_layout.add_widget(amount_input)
        content.add_widget(amount_layout)
        date_layout = BoxLayout(size_hint_y=0.15)
        date_layout.add_widget(CLabel(text='日期:', size_hint_x=0.3))
        date_input = CTextInput(text=row['date'].strftime('%Y-%m-%d'), hint_text='YYYY-MM-DD', multiline=False, size_hint_x=0.7)
        date_layout.add_widget(date_input)
        content.add_widget(date_layout)
        note_layout = BoxLayout(size_hint_y=0.15)
        note_layout.add_widget(CLabel(text='備註:', size_hint_x=0.3))
        note_input = CTextInput(text=row['notes'], multiline=False, size_hint_x=0.7)
        note_layout.add_widget(note_input)
        content.add_widget(note_layout)
        buttons_layout = BoxLayout(size_hint_y=0.15, spacing=dp(10))
        cancel_button = CButton(text='取消')
        save_button = CButton(text='儲存')
        buttons_layout.add_widget(cancel_button)
        buttons_layout.add_widget(save_button)
        content.add_widget(buttons_layout)
        type_spinner.bind(text=lambda spinner, text: setattr(category_spinner, 'values', INCOME_CATEGORIES if text == '收入' else EXPENSE_CATEGORIES))
        popup = Popup(title='編輯交易', content=content, size_hint=(0.6, 0.6), auto_dismiss=False)
        cancel_button.bind(on_press=popup.dismiss)
        save_button.bind(on_press=lambda btn: self._save_transaction(index, popup, type_spinner.text, category_spinner.text, amount_input.text, note_input.text, date_input.text))
        popup.open()

    def _save_transaction(self, index, popup, t_type, category, amount_text, note, date_text):
        try:
            amount = float(amount_text) if amount_text else 0
            date = datetime.strptime(date_text, '%Y-%m-%d')
            if amount <= 0:
                Popup(title='錯誤', content=CLabel(text='請輸入有效金額'), size_hint=(0.4, 0.2)).open()
                return
            success = self.finance_data.update_transaction(index, t_type, category, amount, note, date)
            if success:
                popup.dismiss()
                self._update_summary()
                self._update_advice()
                self._load_recent_transactions()
                Popup(title='成功', content=CLabel(text='交易已更新'), size_hint=(0.4, 0.2)).open()
            else:
                Popup(title='錯誤', content=CLabel(text='更新失敗'), size_hint=(0.4, 0.2)).open()
        except ValueError:
            Popup(title='錯誤', content=CLabel(text='日期格式錯誤 (YYYY-MM-DD)'), size_hint=(0.4, 0.2)).open()

    def _delete_transaction(self, index):
        content = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(10))
        content.add_widget(CLabel(text='確定刪除此交易？'))
        buttons = BoxLayout(size_hint_y=0.4, spacing=dp(10))
        cancel_button = CButton(text='取消')
        confirm_button = CButton(text='確認', background_color=THEMES[self.theme]['error'])
        buttons.add_widget(cancel_button)
        buttons.add_widget(confirm_button)
        popup = Popup(title='確認刪除', content=content, size_hint=(0.4, 0.3), auto_dismiss=False)
        cancel_button.bind(on_press=popup.dismiss)
        confirm_button.bind(on_press=lambda btn: self._confirm_delete(index, popup))
        popup.open()

    def _confirm_delete(self, index, popup):
        success = self.finance_data.delete_transaction(index)
        popup.dismiss()
        if success:
            self._update_summary()
            self._update_advice()
            self._load_recent_transactions()
            Popup(title='成功', content=CLabel(text='交易已刪除'), size_hint=(0.4, 0.2)).open()
        else:
            Popup(title='錯誤', content=CLabel(text='刪除失敗'), size_hint=(0.4, 0.2)).open()

    def _exit_app(self, instance):
        App.get_running_app().stop()

    def update_theme(self, theme):
        self.theme = theme
        for widget in self.walk():
            if isinstance(widget, Card):
                widget.update_color(theme)
                widget.bind(pos=widget.update_rect, size=widget.update_rect)
            elif isinstance(widget, CButton) or isinstance(widget, RoundedButton):
                widget.background_color = THEMES[theme]['accent']

class TransactionsScreen(Screen):
    def __init__(self, finance_data, **kwargs):
        super().__init__(**kwargs)
        self.finance_data = finance_data
        self.theme = 'light'
        self.layout = BoxLayout(orientation='vertical', padding=dp(15), spacing=dp(10))
        
        # Title
        title_card = Card(bg_color=THEMES[self.theme]['card'], orientation='vertical', size_hint_y=0.12, padding=dp(10))
        title_row = BoxLayout(orientation='horizontal')
        title_row.add_widget(CLabel(text="交易記錄", font_size=dp(26), bold=True, color=THEMES[self.theme]['accent'], size_hint_x=0.7))
        self.add_button = RoundedButton(text="新增交易", size_hint=(None, 0.8), width=dp(120))
        self.add_button.bind(on_press=self._open_add_dialog)
        title_row.add_widget(self.add_button)
        title_card.add_widget(title_row)
        title_card.add_widget(CLabel(text="版權所有 by Jack Pan 2025.05.02", font_size=dp(12), color=(0.5,0.5,0.5,1)))
        self.layout.add_widget(title_card)

        # Filter
        self.filter_layout = BoxLayout(orientation='horizontal', size_hint_y=0.1, spacing=dp(10))
        self.filter_layout.add_widget(CLabel(text="日期範圍:", size_hint_x=0.1))
        self.start_date_input = CTextInput(hint_text='YYYY-MM-DD', multiline=False, size_hint_x=0.2)
        self.end_date_input = CTextInput(hint_text='YYYY-MM-DD', multiline=False, size_hint_x=0.2)
        self.type_spinner = CSpinner(text='全部類型', values=('全部類型', '收入', '支出'), size_hint_x=0.15)
        self.category_spinner = CSpinner(text='全部類別', values=['全部類別'] + INCOME_CATEGORIES + EXPENSE_CATEGORIES, size_hint_x=0.15)
        self.filter_button = RoundedButton(text="篩選", size_hint_x=0.1)
        self.reset_button = RoundedButton(text="重設", size_hint_x=0.1)
        self.filter_layout.add_widget(self.start_date_input)
        self.filter_layout.add_widget(self.end_date_input)
        self.filter_layout.add_widget(self.type_spinner)
        self.filter_layout.add_widget(self.category_spinner)
        self.filter_layout.add_widget(self.filter_button)
        self.filter_layout.add_widget(self.reset_button)
        self.layout.add_widget(self.filter_layout)

        # Header
        self.header_layout = GridLayout(cols=6, size_hint_y=0.08, padding=[dp(5), dp(5)])
        headers = [('日期', 0.15), ('類型', 0.1), ('類別', 0.15), ('金額', 0.15), ('備註', 0.3), ('操作', 0.15)]
        for header, size in headers:
            self.header_layout.add_widget(CLabel(text=header, bold=True, size_hint_x=size))
        self.layout.add_widget(self.header_layout)

        # Transactions
        self.scroll_view = ScrollView(size_hint_y=0.55, do_scroll_y=True)
        self.transactions_layout = GridLayout(cols=1, spacing=dp(5), size_hint_y=None)
        self.transactions_layout.bind(minimum_height=self.transactions_layout.setter('height'))
        self.scroll_view.add_widget(self.transactions_layout)
        self.layout.add_widget(self.scroll_view)

        # Export and Exit
        buttons_layout = BoxLayout(orientation='horizontal', size_hint_y=0.07, spacing=dp(10))
        export_btn = RoundedButton(text="匯出CSV", size_hint_x=0.5)
        export_btn.bind(on_press=self._export_data)
        exit_btn = RoundedButton(text="離開程式", size_hint_x=0.5, background_color=THEMES[self.theme]['error'])
        exit_btn.bind(on_press=self._exit_app)
        buttons_layout.add_widget(export_btn)
        buttons_layout.add_widget(exit_btn)
        self.layout.add_widget(buttons_layout)
        self.add_widget(self.layout)
        self.filter_button.bind(on_press=self._apply_filter)
        self.reset_button.bind(on_press=self._reset_filter)
        Clock.schedule_once(self._load_transactions, 0)

    def _load_transactions(self, dt=None):
        self.transactions_layout.clear_widgets()
        try:
            start_date = datetime.strptime(self.start_date_input.text, '%Y-%m-%d') if self.start_date_input.text else None
            end_date = datetime.strptime(self.end_date_input.text, '%Y-%m-%d') + timedelta(days=1) if self.end_date_input.text else None
        except ValueError:
            Popup(title='錯誤', content=CLabel(text='日期格式錯誤 (YYYY-MM-DD)'), size_hint=(0.4, 0.2)).open()
            return
        transactions = self.finance_data.get_transactions(start_date, end_date)
        if self.type_spinner.text != '全部類型':
            transactions = transactions[transactions['type'] == self.type_spinner.text]
        if self.category_spinner.text != '全部類別':
            transactions = transactions[transactions['category'] == self.category_spinner.text]
        if transactions.empty:
            self.transactions_layout.add_widget(CLabel(text="無交易記錄", size_hint_y=None, height=dp(40)))
        else:
            for i, (idx, row) in enumerate(transactions.iterrows()):
                item = TransactionItem(i, row['date'], row['type'], row['category'], row['amount'], row['notes'])
                item.edit_button.bind(on_press=lambda btn, index=idx: self._edit_transaction(index))
                item.delete_button.bind(on_press=lambda btn, index=idx: self._delete_transaction(index))
                self.transactions_layout.add_widget(item)
        Clock.schedule_once(lambda dt: setattr(self.scroll_view, 'scroll_y', 1), 0.1)

    def _apply_filter(self, instance):
        self._load_transactions()

    def _reset_filter(self, instance):
        self.start_date_input.text = ''
        self.end_date_input.text = ''
        self.type_spinner.text = '全部類型'
        self.category_spinner.text = '全部類別'
        self._load_transactions()

    def _open_add_dialog(self, instance):
        content = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(10))
        type_layout = BoxLayout(size_hint_y=0.15)
        type_layout.add_widget(CLabel(text='交易類型:', size_hint_x=0.3))
        type_spinner = CSpinner(text='收入', values=('收入', '支出'), size_hint_x=0.7)
        type_layout.add_widget(type_spinner)
        content.add_widget(type_layout)
        category_layout = BoxLayout(size_hint_y=0.15)
        category_layout.add_widget(CLabel(text='交易類別:', size_hint_x=0.3))
        category_spinner = CSpinner(text=INCOME_CATEGORIES[0], values=INCOME_CATEGORIES, size_hint_x=0.7)
        category_layout.add_widget(category_spinner)
        content.add_widget(category_layout)
        amount_layout = BoxLayout(size_hint_y=0.15)
        amount_layout.add_widget(CLabel(text='金額:', size_hint_x=0.3))
        amount_input = CTextInput(hint_text='輸入金額', input_filter='float', multiline=False, size_hint_x=0.7)
        amount_layout.add_widget(amount_input)
        content.add_widget(amount_layout)
        date_layout = BoxLayout(size_hint_y=0.15)
        date_layout.add_widget(CLabel(text='日期:', size_hint_x=0.3))
        date_input = CTextInput(text=datetime.now().strftime('%Y-%m-%d'), hint_text='YYYY-MM-DD', multiline=False, size_hint_x=0.7)
        date_layout.add_widget(date_input)
        content.add_widget(date_layout)
        note_layout = BoxLayout(size_hint_y=0.15)
        note_layout.add_widget(CLabel(text='備註:', size_hint_x=0.3))
        note_input = CTextInput(hint_text='備註 (可選)', multiline=False, size_hint_x=0.7)
        note_layout.add_widget(note_input)
        content.add_widget(note_layout)
        buttons_layout = BoxLayout(size_hint_y=0.15, spacing=dp(10))
        cancel_button = CButton(text='取消')
        add_button = CButton(text='新增')
        buttons_layout.add_widget(cancel_button)
        buttons_layout.add_widget(add_button)
        content.add_widget(buttons_layout)
        type_spinner.bind(text=lambda spinner, text: setattr(category_spinner, 'values', INCOME_CATEGORIES if text == '收入' else EXPENSE_CATEGORIES))
        popup = Popup(title='新增交易', content=content, size_hint=(0.6, 0.6), auto_dismiss=False)
        cancel_button.bind(on_press=popup.dismiss)
        add_button.bind(on_press=lambda btn: self._add_transaction(popup, type_spinner.text, category_spinner.text, amount_input.text, note_input.text, date_input.text))
        popup.open()

    def _add_transaction(self, popup, t_type, category, amount_text, note, date_text):
        try:
            amount = float(amount_text) if amount_text else 0
            date = datetime.strptime(date_text, '%Y-%m-%d')
            if amount <= 0:
                Popup(title='錯誤', content=CLabel(text='請輸入有效金額'), size_hint=(0.4, 0.2)).open()
                return
            success = self.finance_data.add_transaction(t_type, category, amount, note, date)
            if success:
                popup.dismiss()
                self._load_transactions()
                Popup(title='成功', content=CLabel(text='交易已新增'), size_hint=(0.4, 0.2)).open()
            else:
                Popup(title='錯誤', content=CLabel(text='新增失敗'), size_hint=(0.4, 0.2)).open()
        except ValueError:
            Popup(title='錯誤', content=CLabel(text='日期格式錯誤 (YYYY-MM-DD)'), size_hint=(0.4, 0.2)).open()

    def _edit_transaction(self, index):
        row = self.finance_data.df.loc[index]
        content = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(10))
        type_layout = BoxLayout(size_hint_y=0.15)
        type_layout.add_widget(CLabel(text='交易類型:', size_hint_x=0.3))
        type_spinner = CSpinner(text=row['type'], values=('收入', '支出'), size_hint_x=0.7)
        type_layout.add_widget(type_spinner)
        content.add_widget(type_layout)
        category_layout = BoxLayout(size_hint_y=0.15)
        category_layout.add_widget(CLabel(text='交易類別:', size_hint_x=0.3))
        category_spinner = CSpinner(text=row['category'], values=INCOME_CATEGORIES if row['type'] == '收入' else EXPENSE_CATEGORIES, size_hint_x=0.7)
        category_layout.add_widget(category_spinner)
        content.add_widget(category_layout)
        amount_layout = BoxLayout(size_hint_y=0.15)
        amount_layout.add_widget(CLabel(text='金額:', size_hint_x=0.3))
        amount_input = CTextInput(text=str(row['amount']), input_filter='float', multiline=False, size_hint_x=0.7)
        amount_layout.add_widget(amount_input)
        content.add_widget(amount_layout)
        date_layout = BoxLayout(size_hint_y=0.15)
        date_layout.add_widget(CLabel(text='日期:', size_hint_x=0.3))
        date_input = CTextInput(text=row['date'].strftime('%Y-%m-%d'), hint_text='YYYY-MM-DD', multiline=False, size_hint_x=0.7)
        date_layout.add_widget(date_input)
        content.add_widget(date_layout)
        note_layout = BoxLayout(size_hint_y=0.15)
        note_layout.add_widget(CLabel(text='備註:', size_hint_x=0.3))
        note_input = CTextInput(text=row['notes'], multiline=False, size_hint_x=0.7)
        note_layout.add_widget(note_input)
        content.add_widget(note_layout)
        buttons_layout = BoxLayout(size_hint_y=0.15, spacing=dp(10))
        cancel_button = CButton(text='取消')
        save_button = CButton(text='儲存')
        buttons_layout.add_widget(cancel_button)
        buttons_layout.add_widget(save_button)
        content.add_widget(buttons_layout)
        type_spinner.bind(text=lambda spinner, text: setattr(category_spinner, 'values', INCOME_CATEGORIES if text == '收入' else EXPENSE_CATEGORIES))
        popup = Popup(title='編輯交易', content=content, size_hint=(0.6, 0.6), auto_dismiss=False)
        cancel_button.bind(on_press=popup.dismiss)
        save_button.bind(on_press=lambda btn: self._save_transaction(index, popup, type_spinner.text, category_spinner.text, amount_input.text, note_input.text, date_input.text))
        popup.open()

    def _save_transaction(self, index, popup, t_type, category, amount_text, note, date_text):
        try:
            amount = float(amount_text) if amount_text else 0
            date = datetime.strptime(date_text, '%Y-%m-%d')
            if amount <= 0:
                Popup(title='錯誤', content=CLabel(text='請輸入有效金額'), size_hint=(0.4, 0.2)).open()
                return
            success = self.finance_data.update_transaction(index, t_type, category, amount, note, date)
            if success:
                popup.dismiss()
                self._load_transactions()
                Popup(title='成功', content=CLabel(text='交易已更新'), size_hint=(0.4, 0.2)).open()
            else:
                Popup(title='錯誤', content=CLabel(text='更新失敗'), size_hint=(0.4, 0.2)).open()
        except ValueError:
            Popup(title='錯誤', content=CLabel(text='日期格式錯誤 (YYYY-MM-DD)'), size_hint=(0.4, 0.2)).open()

    def _delete_transaction(self, index):
        content = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(10))
        content.add_widget(CLabel(text='確定刪除此交易？'))
        buttons = BoxLayout(size_hint_y=0.4, spacing=dp(10))
        cancel_button = CButton(text='取消')
        confirm_button = CButton(text='確認', background_color=THEMES[self.theme]['error'])
        buttons.add_widget(cancel_button)
        buttons.add_widget(confirm_button)
        content.add_widget(buttons)
        popup = Popup(title='確認刪除', content=content, size_hint=(0.4, 0.3), auto_dismiss=False)
        cancel_button.bind(on_press=popup.dismiss)
        confirm_button.bind(on_press=lambda btn: self._confirm_delete(index, popup))
        popup.open()

    def _confirm_delete(self, index, popup):
        success = self.finance_data.delete_transaction(index)
        popup.dismiss()
        if success:
            self._load_transactions()
            Popup(title='成功', content=CLabel(text='交易已刪除'), size_hint=(0.4, 0.2)).open()
        else:
            Popup(title='錯誤', content=CLabel(text='刪除失敗'), size_hint=(0.4, 0.2)).open()

    def _export_data(self, instance):
        filename = f"finance_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        success = self.finance_data.export_to_csv(filename)
        Popup(title='結果', content=CLabel(text=f'匯出{"成功" if success else "失敗"}'), size_hint=(0.4, 0.2)).open()

    def _exit_app(self, instance):
        App.get_running_app().stop()

    def update_theme(self, theme):
        self.theme = theme
        for widget in self.walk():
            if isinstance(widget, Card):
                widget.update_color(theme)
                widget.bind(pos=widget.update_rect, size=widget.update_rect)
            elif isinstance(widget, CButton) or isinstance(widget, RoundedButton):
                widget.background_color = THEMES[theme]['accent']

class BudgetScreen(Screen):
    def __init__(self, finance_data, **kwargs):
        super().__init__(**kwargs)
        self.finance_data = finance_data
        self.theme = 'light'
        self.layout = BoxLayout(orientation='vertical', padding=dp(15), spacing=dp(10))
        
        # Title
        title_card = Card(bg_color=THEMES[self.theme]['card'], orientation='vertical', size_hint_y=0.12, padding=dp(10))
        title_card.add_widget(CLabel(text="預算管理", font_size=dp(26), bold=True, color=THEMES[self.theme]['accent']))
        title_card.add_widget(CLabel(text="版權所有 by Jack Pan 2025.05.02", font_size=dp(12), color=(0.5,0.5,0.5,1)))
        self.layout.add_widget(title_card)

        # Budget Settings
        budget_card = Card(bg_color=THEMES[self.theme]['card'], orientation='vertical', size_hint_y=0.35, padding=dp(10))
        budget_card.add_widget(CLabel(text="設定每月預算", font_size=dp(18), size_hint_y=0.1))
        form = GridLayout(cols=3, spacing=dp(10), size_hint_y=0.9)
        for category in EXPENSE_CATEGORIES:
            form.add_widget(CLabel(text=category, size_hint_x=0.3))
            budget_input = CTextInput(hint_text='輸入金額', input_filter='float', multiline=False, size_hint_x=0.5)
            budget_input.text = str(self.finance_data.budgets.get(category, 0))
            save_btn = RoundedButton(text='儲存', size_hint_x=0.2)
            save_btn.bind(on_press=lambda btn, cat=category, inp=budget_input: self._save_budget(cat, inp.text))
            form.add_widget(budget_input)
            form.add_widget(save_btn)
        budget_card.add_widget(form)
        self.layout.add_widget(budget_card)

        # Budget Comparison
        comparison_card = Card(bg_color=THEMES[self.theme]['card'], orientation='vertical', size_hint_y=0.45, padding=dp(10))
        comparison_card.add_widget(CLabel(text="本月預算比較", font_size=dp(18), size_hint_y=0.1))
        self.comparison_scroll = ScrollView(size_hint_y=0.9)
        self.comparison_table = GridLayout(cols=5, spacing=dp(5), size_hint_y=None)
        self.comparison_table.bind(minimum_height=self.comparison_table.setter('height'))
        self.comparison_scroll.add_widget(self.comparison_table)
        comparison_card.add_widget(self.comparison_scroll)
        self.layout.add_widget(comparison_card)

        # Exit
        exit_btn = RoundedButton(text="離開程式", size_hint=(1, 0.07), background_color=THEMES[self.theme]['error'])
        exit_btn.bind(on_press=self._exit_app)
        self.layout.add_widget(exit_btn)
        self.add_widget(self.layout)
        Clock.schedule_once(self._update_comparison, 0)

    def _save_budget(self, category, amount_text):
        try:
            amount = float(amount_text) if amount_text else 0
            if amount < 0:
                Popup(title='錯誤', content=CLabel(text='預算不能為負數'), size_hint=(0.4, 0.2)).open()
                return
            success = self.finance_data.update_budget(category, amount)
            if success:
                self._update_comparison()
                Popup(title='成功', content=CLabel(text='預算已更新'), size_hint=(0.4, 0.2)).open()
            else:
                Popup(title='錯誤', content=CLabel(text='更新失敗'), size_hint=(0.4, 0.2)).open()
        except ValueError:
            Popup(title='錯誤', content=CLabel(text='請輸入有效金額'), size_hint=(0.4, 0.2)).open()

    def _update_comparison(self, dt=None):
        self.comparison_table.clear_widgets()
        headers = ['類別', '預算', '實際支出', '剩餘', '百分比']
        for header in headers:
            self.comparison_table.add_widget(CLabel(text=header, bold=True, size_hint_y=None, height=dp(40)))
        comparison = self.finance_data.get_budget_comparison()
        for category, data in comparison.items():
            self.comparison_table.add_widget(CLabel(text=category, size_hint_y=None, height=dp(40)))
            self.comparison_table.add_widget(CLabel(text=f"{data['budget']:,.0f}", size_hint_y=None, height=dp(40)))
            self.comparison_table.add_widget(CLabel(text=f"{data['actual']:,.0f}", size_hint_y=None, height=dp(40)))
            self.comparison_table.add_widget(CLabel(text=f"{data['remaining']:,.0f}", size_hint_y=None, height=dp(40)))
            self.comparison_table.add_widget(CLabel(text=f"{data['percentage']:.1f}%", size_hint_y=None, height=dp(40), color=(0.8, 0, 0, 1) if data['percentage'] > 100 else (0, 0.7, 0, 1)))

    def _exit_app(self, instance):
        App.get_running_app().stop()

    def update_theme(self, theme):
        self.theme = theme
        for widget in self.walk():
            if isinstance(widget, Card):
                widget.update_color(theme)
                widget.bind(pos=widget.update_rect, size=widget.update_rect)
            elif isinstance(widget, CButton) or isinstance(widget, RoundedButton):
                widget.background_color = THEMES[theme]['accent']

class AnalysisScreen(Screen):
    def __init__(self, finance_data, budget_advisor, **kwargs):
        super().__init__(**kwargs)
        self.finance_data = finance_data
        self.budget_advisor = budget_advisor
        self.theme = 'light'
        self.layout = BoxLayout(orientation='vertical', padding=dp(15), spacing=dp(10))
        
        # Title
        title_card = Card(bg_color=THEMES[self.theme]['card'], orientation='vertical', size_hint_y=0.12, padding=dp(10))
        title_card.add_widget(CLabel(text="財務分析", font_size=dp(26), bold=True, color=THEMES[self.theme]['accent']))
        title_card.add_widget(CLabel(text="版權所有 by Jack Pan 2025.05.02", font_size=dp(12), color=(0.5,0.5,0.5,1)))
        self.layout.add_widget(title_card)

        # Charts
        self.chart_layout = BoxLayout(orientation='vertical', size_hint_y=0.75)
        self.layout.add_widget(self.chart_layout)

        # Exit
        exit_btn = RoundedButton(text="離開程式", size_hint=(1, 0.07), background_color=THEMES[self.theme]['error'])
        exit_btn.bind(on_press=self._exit_app)
        self.layout.add_widget(exit_btn)
        self.add_widget(self.layout)
        Clock.schedule_once(self._load_analysis_charts, 0)

    def _load_analysis_charts(self, dt=None):
        self.chart_layout.clear_widgets()
        if FigureCanvasKivyAgg is None:
            self.chart_layout.add_widget(CLabel(text="請安裝 kivy-garden matplotlib", color=(1,0,0,1), font_size=dp(14)))
            logging.error("kivy-garden-matplotlib not installed")
            return

        # Log all available data for debugging
        logging.info(f"All Finance Data: {self.finance_data.df.to_dict()}")
        logging.info(f"Budgets: {self.finance_data.budgets}")

        # Cash Flow (Check all available data, not just current month)
        cash_flow = self.finance_data.get_transactions()
        if not cash_flow.empty:
            cash_flow['date'] = pd.to_datetime(cash_flow['date'])
            monthly_cash_flow = cash_flow.groupby(cash_flow['date'].dt.strftime('%Y-%m')).agg({'amount': ['sum']})
            monthly_cash_flow.columns = ['amount']
            monthly_cash_flow['income'] = monthly_cash_flow['amount'].where(cash_flow['type'] == '收入', 0).groupby(cash_flow['date'].dt.strftime('%Y-%m')).sum()
            monthly_cash_flow['expense'] = monthly_cash_flow['amount'].where(cash_flow['type'] == '支出', 0).groupby(cash_flow['date'].dt.strftime('%Y-%m')).sum()
            logging.info(f"Monthly Cash Flow: {monthly_cash_flow.to_dict()}")
            if not monthly_cash_flow['income'].empty or not monthly_cash_flow['expense'].empty:
                try:
                    fig1, ax1 = plt.subplots(figsize=(8, 3))
                    monthly_cash_flow['income'].plot(kind='bar', ax=ax1, color='green', label='收入', position=0, width=0.4)
                    monthly_cash_flow['expense'].plot(kind='bar', ax=ax1, color='red', label='支出', position=1, width=0.4)
                    ax1.set_title('月度現金流', fontsize=12)
                    ax1.set_xlabel('月份', fontsize=10)
                    ax1.set_ylabel('金額 (元)', fontsize=10)
                    ax1.legend()
                    ax1.tick_params(axis='x', rotation=45)
                    plt.tight_layout()
                    chart_widget = FigureCanvasKivyAgg(fig1)
                    self.chart_layout.add_widget(chart_widget)
                    logging.info("Cash Flow chart added successfully")
                except Exception as e:
                    self.chart_layout.add_widget(CLabel(text=f"現金流圖表生成失敗: {str(e)}", color=(1,0,0,1), font_size=dp(14)))
                    logging.error(f"Failed to generate Cash Flow chart: {e}")
            else:
                self.chart_layout.add_widget(CLabel(text="無現金流數據", color=(1,0,0,1), font_size=dp(14)))
                logging.info("No cash flow data available after grouping")
        else:
            self.chart_layout.add_widget(CLabel(text="無交易數據", color=(1,0,0,1), font_size=dp(14)))
            logging.info("No transaction data available")

        # Expense Categories
        expense_df = self.finance_data.df[self.finance_data.df['type'] == '支出']
        logging.info(f"Expense Data: {expense_df.to_dict()}")
        if not expense_df.empty:
            try:
                fig2, ax2 = plt.subplots(figsize=(8, 3))
                expense_df.groupby('category')['amount'].sum().plot(kind='pie', autopct='%1.1f%%', ax=ax2, textprops={'fontsize': 8})
                ax2.set_title('支出類別比例', fontsize=12)
                plt.tight_layout()
                chart_widget = FigureCanvasKivyAgg(fig2)
                self.chart_layout.add_widget(chart_widget)
                logging.info("Expense Categories chart added successfully")
            except Exception as e:
                self.chart_layout.add_widget(CLabel(text=f"支出類別圖表生成失敗: {str(e)}", color=(1,0,0,1), font_size=dp(14)))
                logging.error(f"Failed to generate Expense Categories chart: {e}")
        else:
            self.chart_layout.add_widget(CLabel(text="無支出數據", color=(1,0,0,1), font_size=dp(14)))
            logging.info("No expense data available")

        # Budget Comparison
        budget_comparison = self.finance_data.get_budget_comparison()
        logging.info(f"Budget Comparison Data: {budget_comparison}")
        if budget_comparison and any(v['budget'] > 0 or v['actual'] > 0 for v in budget_comparison.values()):
            try:
                categories = list(budget_comparison.keys())
                budgets = [v['budget'] for v in budget_comparison.values()]
                actuals = [v['actual'] for v in budget_comparison.values()]
                logging.info(f"Categories: {categories}, Budgets: {budgets}, Actuals: {actuals}")
                fig3, ax3 = plt.subplots(figsize=(8, 3))
                x = np.arange(len(categories))
                ax3.bar(x - 0.2, budgets, 0.4, label='預算', color='blue')
                ax3.bar(x + 0.2, actuals, 0.4, label='實際', color='orange')
                ax3.set_xticks(x)
                ax3.set_xticklabels(categories, rotation=45, fontsize=8)
                ax3.set_title('預算 vs 實際支出', fontsize=12)
                ax3.set_ylabel('金額 (元)', fontsize=10)
                max_value = max(max(budgets, default=0), max(actuals, default=0))
                ax3.set_ylim(0, max_value * 1.2 if max_value > 0 else 1000)
                ax3.legend()
                plt.tight_layout()
                chart_widget = FigureCanvasKivyAgg(fig3)
                self.chart_layout.add_widget(chart_widget)
                logging.info("Budget Comparison chart added successfully")
            except Exception as e:
                self.chart_layout.add_widget(CLabel(text=f"預算比較圖表生成失敗: {str(e)}", color=(1,0,0,1), font_size=dp(14)))
                logging.error(f"Failed to generate Budget Comparison chart: {e}")
        else:
            self.chart_layout.add_widget(CLabel(text="無預算或實際支出數據，請在'預算管理'中設置預算", color=(1,0,0,1), font_size=dp(14)))
            logging.info("No budget or actual expense data available")

    def _exit_app(self, instance):
        App.get_running_app().stop()

    def update_theme(self, theme):
        self.theme = theme
        for widget in self.walk():
            if isinstance(widget, Card):
                widget.update_color(theme)
                widget.bind(pos=widget.update_rect, size=widget.update_rect)
            elif isinstance(widget, CButton) or isinstance(widget, RoundedButton):
                widget.background_color = THEMES[theme]['accent']

class SettingsScreen(Screen):
    def __init__(self, finance_data, **kwargs):
        super().__init__(**kwargs)
        self.finance_data = finance_data
        self.theme = 'light'
        self.layout = BoxLayout(orientation='vertical', padding=dp(15), spacing=dp(10))
        
        # Title
        title_card = Card(bg_color=THEMES[self.theme]['card'], orientation='vertical', size_hint_y=0.12, padding=dp(10))
        title_card.add_widget(CLabel(text="設定", font_size=dp(26), bold=True, color=THEMES[self.theme]['accent']))
        title_card.add_widget(CLabel(text="版權所有 by Jack Pan 2025.05.02", font_size=dp(12), color=(0.5,0.5,0.5,1)))
        self.layout.add_widget(title_card)

        # Theme Selection
        theme_card = Card(bg_color=THEMES[self.theme]['card'], orientation='vertical', size_hint_y=0.2, padding=dp(10))
        theme_card.add_widget(CLabel(text="主題選擇", font_size=dp(18), size_hint_y=0.3))
        theme_layout = BoxLayout(orientation='horizontal', size_hint_y=0.7, spacing=dp(10))
        self.theme_spinner = CSpinner(text='Light', values=('Light', 'Dark'), size_hint_x=0.5)
        theme_btn = RoundedButton(text='應用', size_hint_x=0.5)
        theme_btn.bind(on_press=self._apply_theme)
        theme_layout.add_widget(self.theme_spinner)
        theme_layout.add_widget(theme_btn)
        theme_card.add_widget(theme_layout)
        self.layout.add_widget(theme_card)

        # Backup
        backup_card = Card(bg_color=THEMES[self.theme]['card'], orientation='vertical', size_hint_y=0.2, padding=dp(10))
        backup_card.add_widget(CLabel(text="備份與還原", font_size=dp(18), size_hint_y=0.3))
        backup_layout = BoxLayout(orientation='horizontal', size_hint_y=0.7, spacing=dp(10))
        backup_btn = RoundedButton(text='建立備份', size_hint_x=0.5)
        restore_btn = RoundedButton(text='還原備份', size_hint_x=0.5, background_color=THEMES[self.theme]['error'])
        backup_btn.bind(on_press=self._create_backup)
        restore_btn.bind(on_press=self._restore_backup)
        backup_layout.add_widget(backup_btn)
        backup_layout.add_widget(restore_btn)
        backup_card.add_widget(backup_layout)
        self.layout.add_widget(backup_card)

        # Exit
        exit_btn = RoundedButton(text="離開程式", size_hint=(1, 0.07), background_color=THEMES[self.theme]['error'])
        exit_btn.bind(on_press=self._exit_app)
        self.layout.add_widget(exit_btn)
        self.add_widget(self.layout)

    def _apply_theme(self, instance):
        theme = 'dark' if self.theme_spinner.text == 'Dark' else 'light'
        self.theme = theme
        for widget in self.walk():
            if isinstance(widget, Card):
                widget.update_color(theme)
                widget.bind(pos=widget.update_rect, size=widget.update_rect)
            elif isinstance(widget, CButton) or isinstance(widget, RoundedButton):
                widget.background_color = THEMES[theme]['accent']

    def _create_backup(self, instance):
        # 使用 FinanceData.delete_transaction 中的備份邏輯
        backup_filename = f"transactions_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        self.finance_data.df.to_csv(backup_filename, index=False)
        logging.info(f"Backup created: {backup_filename}")
        Popup(title='成功', content=CLabel(text=f'備份已創建至 {backup_filename}'), size_hint=(0.4, 0.2)).open()

    def _restore_backup(self, instance):
        content = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(10))
        content.add_widget(CLabel(text='選擇備份文件進行還原:'))
        file_input = CTextInput(hint_text='輸入備份文件路徑', multiline=False, size_hint_y=0.5)
        buttons = BoxLayout(size_hint_y=0.5, spacing=dp(10))
        cancel_button = CButton(text='取消')
        restore_button = CButton(text='還原', background_color=THEMES[self.theme]['error'])
        buttons.add_widget(cancel_button)
        buttons.add_widget(restore_button)
        content.add_widget(file_input)
        content.add_widget(buttons)
        popup = Popup(title='還原備份', content=content, size_hint=(0.5, 0.3), auto_dismiss=False)
        cancel_button.bind(on_press=popup.dismiss)
        restore_button.bind(on_press=lambda btn: self._confirm_restore(popup, file_input.text))
        popup.open()

    def _confirm_restore(self, popup, filename):
        if os.path.exists(filename):
            try:
                df = pd.read_csv(filename)
                self.finance_data.df = df
                self.finance_data.df.to_csv(self.finance_data.filename, index=False)
                popup.dismiss()
                Popup(title='成功', content=CLabel(text='還原完成'), size_hint=(0.4, 0.2)).open()
                logging.info(f"Restored from {filename}")
            except Exception as e:
                Popup(title='錯誤', content=CLabel(text=f'還原失敗: {str(e)}'), size_hint=(0.4, 0.2)).open()
                logging.error(f"Restore failed: {e}")
        else:
            Popup(title='錯誤', content=CLabel(text='文件不存在'), size_hint=(0.4, 0.2)).open()

    def _exit_app(self, instance):
        App.get_running_app().stop()

    def update_theme(self, theme):
        self.theme = theme
        for widget in self.walk():
            if isinstance(widget, Card):
                widget.update_color(theme)
                widget.bind(pos=widget.update_rect, size=widget.update_rect)
            elif isinstance(widget, CButton) or isinstance(widget, RoundedButton):
                widget.background_color = THEMES[theme]['accent']

class FinanceApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.finance_data = FinanceData()
        self.budget_advisor = BudgetAdvisor(self.finance_data)

    def build(self):
        self.title = "財務管理"  # 應用程式標題
        Window.clearcolor = THEMES['light']['background']
        sm = TabbedPanel(do_default_tab=False)
        # 為每個螢幕創建 TabbedPanelItem 並添加
        home_tab = TabbedPanelItem(text='首頁')
        home_tab.add_widget(HomeScreen(self.finance_data, self.budget_advisor, name='home'))
        sm.add_widget(home_tab)

        transactions_tab = TabbedPanelItem(text='交易記錄')
        transactions_tab.add_widget(TransactionsScreen(self.finance_data, name='transactions'))
        sm.add_widget(transactions_tab)

        budget_tab = TabbedPanelItem(text='預算管理')
        budget_tab.add_widget(BudgetScreen(self.finance_data, name='budget'))
        sm.add_widget(budget_tab)

        analysis_tab = TabbedPanelItem(text='財務分析')
        analysis_tab.add_widget(AnalysisScreen(self.finance_data, self.budget_advisor, name='analysis'))
        sm.add_widget(analysis_tab)

        settings_tab = TabbedPanelItem(text='設定')
        settings_tab.add_widget(SettingsScreen(self.finance_data, name='settings'))
        sm.add_widget(settings_tab)

        # 設置預設標籤為第一個標籤
        sm.default_tab = home_tab
        return sm
    
        #sm.add_widget(HomeScreen(self.finance_data, self.budget_advisor, name='home'))
        #sm.add_widget(TransactionsScreen(self.finance_data, name='transactions'))
        #sm.add_widget(BudgetScreen(self.finance_data, name='budget'))
        #sm.add_widget(AnalysisScreen(self.finance_data, self.budget_advisor, name='analysis'))
        #sm.add_widget(SettingsScreen(self.finance_data, name='settings'))
        #sm.default_tab = sm.get_tab_list()[0]
        #return sm

    def on_start(self):
        signal.signal(signal.SIGINT, self._handle_interrupt)
        Clock.schedule_once(self.center_window, 0)
        logging.info("App started successfully")

    def center_window(self, dt):
            # 獲取螢幕尺寸並計算中心位置
        screen_width, screen_height = Window.system_size
        window_width, window_height = Window.size
        Window.left = max(0, (screen_width - window_width) / 2)  # 確保不超出螢幕左邊界
        Window.top = max(0, (screen_height - window_height) / 2)  # 確保不超出螢幕頂部
       # print(f"Screen: {screen_width}x{screen_height}, Window: {window_width}x{window_height}, Left: {left}, Top: {top}")
        #Window.left = left
        #Window.top = top

    def _handle_interrupt(self, signum, frame):
        logging.info("App interrupted, exiting gracefully")
        self.stop()

if __name__ == "__main__":
    FinanceApp().run()
