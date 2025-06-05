from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.conf import settings 
from unittest.mock import patch, MagicMock 
from decimal import Decimal
from django.utils import timezone

from .models import UserProfile, Cryptocurrency, Holding, Transaction 
from .forms import TransactionForm 

class CoreAuthViewsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.register_url = reverse('core:register')
        self.login_url = reverse('core:login') 
        self.logout_url = reverse('core:logout')
        self.dashboard_url = reverse('core:dashboard')
        self.index_url = reverse('core:index')
        self.test_user_username = 'testuser_trans_hist' 
        self.test_user_email = 'test_trans_hist@example.com'
        self.test_user_password = 'StrongPassword123!trans_hist' 
        self.user = User.objects.create_user(
            username=self.test_user_username,
            email=self.test_user_email,
            password=self.test_user_password
        )
        self.user_profile = UserProfile.objects.get(user=self.user)


    def test_index_view_get(self):
        response = self.client.get(self.index_url)
        self.assertEqual(response.status_code, 200)
    def test_register_view_get(self):
        response = self.client.get(self.register_url)
        self.assertEqual(response.status_code, 200)
    def test_login_view_get(self):
        response = self.client.get(self.login_url)
        self.assertEqual(response.status_code, 200)
    
    @override_settings(LOGIN_URL='/login/') 
    def test_dashboard_view_redirects_if_not_logged_in(self):
        self.client.logout() 
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 302) 
        self.assertTrue(response.url.startswith(settings.LOGIN_URL)) 
        self.assertIn(f"?next={self.dashboard_url}", response.url)
        login_page_response = self.client.get(response.url)
        self.assertEqual(login_page_response.status_code, 200, f"Login page {response.url} did not return 200.")

    def test_dashboard_view_accessible_if_logged_in(self):
        self.client.login(username=self.test_user_username, password=self.test_user_password)
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 200)

    def test_logout_view(self):
        self.client.login(username=self.test_user_username, password=self.test_user_password)
        response = self.client.get(self.logout_url, follow=True)
        self.assertRedirects(response, self.index_url)

    def test_successful_registration_logs_in_and_redirects(self):
        new_username = 'reg_trans_hist_ok' 
        new_email = f'{new_username}@example.com'
        new_password = 'YetAnotherStrongPassword123!!!TransHist' 
        
        response = self.client.post(self.register_url, {
            'username': new_username, 'email': new_email,
            'first_name': 'RegTransHist', 'last_name': 'TestTransHist',
            'password': new_password, 'password2': new_password, 
        }) 
        self.assertEqual(response.status_code, 302, f"Form errors: {response.context.get('form').errors.as_data() if response.context and hasattr(response.context.get('form'), 'errors') else 'No form/errors in context'}")
        self.assertRedirects(response, self.dashboard_url, fetch_redirect_response=False)


class BinanceAPITests(TestCase):
    def setUp(self):
        self.client_django = Client()
        self.user = User.objects.create_user(username='binance_trans_hist', password='testpasswordenv_trans_hist', email='btest_trans_hist@example.com')
        self.client_django.login(username='binance_trans_hist', password='testpasswordenv_trans_hist')
        self.binance_test_url = reverse('core:binance_test')

    @patch('core.views.Client') 
    def test_binance_test_view_success_with_env_vars(self, MockBinanceApiClient):
        mock_instance = MockBinanceApiClient.return_value
        mock_instance.get_server_time.return_value = {'serverTime': 1678886400000}
        mock_instance.get_account.return_value = {'balances': [], 'canTrade': True, 'accountType': 'SPOT'}
        with self.settings(BINANCE_API_KEY='env_fake_key', BINANCE_API_SECRET='env_fake_secret', BINANCE_TESTNET=False):
            response = self.client_django.get(self.binance_test_url)
        self.assertEqual(response.status_code, 200)

class CoreModelsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='modeltester_trans_hist', password='password_trans_hist', email='model_trans_hist@test.com')
        self.user_profile = UserProfile.objects.get(user=self.user) 
        self.btc = Cryptocurrency.objects.create(symbol='BTC', name='Bitcoin', current_price=Decimal('50000.00'), price_currency='USD')
        self.eth = Cryptocurrency.objects.create(symbol='ETH', name='Ethereum', current_price=Decimal('4000.00'), price_currency='USD')

    def test_cryptocurrency_creation(self):
        self.assertEqual(str(self.btc), 'Bitcoin (BTC) - 50000.00 USD') 
    def test_holding_properties(self):
        holding = Holding.objects.create(user_profile=self.user_profile, cryptocurrency=self.btc, quantity=Decimal('2.0'), average_buy_price=Decimal('45000.00'))
        self.assertEqual(holding.cost_basis, Decimal('90000.00'))
        self.assertEqual(holding.current_market_value, Decimal('100000.00'))
        self.assertEqual(holding.profit_loss, Decimal('10000.00'))
        self.assertAlmostEqual(holding.profit_loss_percent, (Decimal('10000.00') / Decimal('90000.00')) * 100)

class CoreCryptocurrencyViewsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='cryptoview_trans_hist', email='cryptoview_trans_hist@example.com', password='password123TransHist!')
        cls.crypto1 = Cryptocurrency.objects.create(symbol='XTZ', name='Tezos', current_price=Decimal('3.50'), price_currency='USD')
        cls.list_url = reverse('core:cryptocurrency_list')
    def setUp(self):
        self.client = Client()
        self.client.login(username=self.user.username, password='password123TransHist!') 
    def test_cryptocurrency_list_view_get(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "3,50 USD") 

class DashboardViewTests(TestCase): 
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='dashboard_trans_hist', email='dash_trans_hist@example.com', password='password123_trans_hist')
        self.client.login(username='dashboard_trans_hist', password='password123_trans_hist')
        self.user_profile = UserProfile.objects.get(user=self.user)
        self.btc = Cryptocurrency.objects.create(symbol='BTC', name='Bitcoin', current_price=Decimal('50000.00'))
        self.eth = Cryptocurrency.objects.create(symbol='ETH', name='Ethereum', current_price=Decimal('4000.00')) 
        self.holding_btc = Holding.objects.create(user_profile=self.user_profile, cryptocurrency=self.btc, quantity=Decimal('0.5'), average_buy_price=Decimal('40000.00'))
        self.holding_eth = Holding.objects.create(user_profile=self.user_profile, cryptocurrency=self.eth, quantity=Decimal('10.0'), average_buy_price=Decimal('3000.00')) 
        self.dashboard_url = reverse('core:dashboard')

    def test_dashboard_view_displays_portfolio(self):
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '65000,00 USD') 
        self.assertContains(response, '25,00%')

class TransactionFormViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='transactionuser_hist', email='trans_hist@example.com', password='StrongPasswordTransaction123!hist')
        self.client.login(username='transactionuser_hist', password='StrongPasswordTransaction123!hist')
        self.user_profile = UserProfile.objects.get(user=self.user) 

        self.btc = Cryptocurrency.objects.create(symbol='BTC', name='Bitcoin', current_price=Decimal('50000.00'), price_currency='USD')
        self.eth = Cryptocurrency.objects.create(symbol='ETH', name='Ethereum', current_price=Decimal('4000.00'), price_currency='USD')
        
        self.add_transaction_url = reverse('core:add_transaction')

    def test_add_transaction_view_get(self):
        response = self.client.get(self.add_transaction_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/add_transaction.html')
        self.assertIsInstance(response.context['form'], TransactionForm)

    def test_add_buy_transaction_creates_holding_and_transaction(self):
        transaction_data = {
            'cryptocurrency': self.btc.symbol, 'transaction_type': 'BUY',
            'quantity_crypto': '1.5', 'price_per_unit': '48000.00', 
            'fees': '25.00', 'transaction_date': timezone.now().strftime('%Y-%m-%dT%H:%M'), 
        }
        response = self.client.post(self.add_transaction_url, transaction_data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Transaction.objects.count(), 1)
        holding = Holding.objects.get(user_profile=self.user_profile, cryptocurrency=self.btc)
        self.assertEqual(holding.quantity, Decimal('1.5'))

class TransactionHistoryViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='historyuser_v2', email='history_v2@example.com', password='PasswordHistory123!v2')
        self.client.login(username='historyuser_v2', password='PasswordHistory123!v2')
        self.user_profile = UserProfile.objects.get(user=self.user)

        self.btc = Cryptocurrency.objects.create(symbol='BTC', name='Bitcoin', current_price=Decimal('50000.00'), price_currency='USD')
        self.eth = Cryptocurrency.objects.create(symbol='ETH', name='Ethereum', current_price=Decimal('4000.00'), price_currency='USD')

        self.tx1_date = timezone.now() - timezone.timedelta(days=2)
        self.tx2_date = timezone.now() - timezone.timedelta(days=1)

        self.tx1 = Transaction.objects.create(
            user_profile=self.user_profile, cryptocurrency=self.btc, transaction_type='BUY',
            quantity_crypto=Decimal('0.5'), price_per_unit=Decimal('48000.00'), fees=Decimal('10'),
            transaction_date=self.tx1_date
        )
        self.tx2 = Transaction.objects.create(
            user_profile=self.user_profile, cryptocurrency=self.eth, transaction_type='SELL',
            quantity_crypto=Decimal('2.0'), price_per_unit=Decimal('4100.00'), fees=Decimal('5'),
            transaction_date=self.tx2_date
        )
        self.history_url = reverse('core:transaction_history')

    @override_settings(LOGIN_URL='/login/') 
    def test_transaction_history_view_requires_login(self):
        self.client.logout()
        response = self.client.get(self.history_url)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(settings.LOGIN_URL))

    def test_transaction_history_view_displays_transactions(self):
        response = self.client.get(self.history_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/transaction_history.html')
        self.assertContains(response, 'Histórico de Transações')
        self.assertIn('transactions', response.context)
        self.assertEqual(len(response.context['transactions']), 2)
        
        self.assertEqual(response.context['transactions'][0], self.tx2) # Mais recente primeiro
        self.assertEqual(response.context['transactions'][1], self.tx1)

        self.assertContains(response, self.tx2.cryptocurrency.symbol) 
        self.assertContains(response, 'Venda')
        self.assertContains(response, '2,00000000') 
        self.assertContains(response, '4100,00') 
        self.assertContains(response, '8200,00') 
        self.assertContains(response, '5,00') 

    def test_transaction_history_view_empty(self):
        Transaction.objects.filter(user_profile=self.user_profile).delete()
        response = self.client.get(self.history_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Nenhuma Transação Registrada')
        self.assertEqual(len(response.context['transactions']), 0)

