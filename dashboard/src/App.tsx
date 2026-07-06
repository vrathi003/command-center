import { useEffect, useState } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import { AppShell } from '@/components/layout/AppShell'
import { AccountsPage } from '@/pages/AccountsPage'
import { EmailInboxPage } from '@/pages/EmailInboxPage'
import { AssetDetailPage } from '@/pages/AssetDetailPage'
import { AssetsPage } from '@/pages/AssetsPage'
import { BudgetPage } from '@/pages/BudgetPage'
import { ConstructionPage } from '@/pages/ConstructionPage'
import { CreditCardDetailPage } from '@/pages/CreditCardDetailPage'
import { CreditCardStatementInboxPage } from '@/pages/CreditCardStatementInboxPage'
import { CreditCardStatementPage } from '@/pages/CreditCardStatementPage'
import { CreditCardsPage } from '@/pages/CreditCardsPage'
import { DebtPage } from '@/pages/DebtPage'
import { DashboardPage } from '@/pages/DashboardPage'
import { GoalsPage } from '@/pages/GoalsPage'
import { HomeInventoryPage } from '@/pages/HomeInventoryPage'
import { HomeItemDetailPage } from '@/pages/HomeItemDetailPage'
import { IncomeTaxPage } from '@/pages/IncomeTaxPage'
import { InsurancePage } from '@/pages/InsurancePage'
import { InvestmentsPage } from '@/pages/InvestmentsPage'
import { JournalPage } from '@/pages/JournalPage'
import { MerchantRulesPage } from '@/pages/MerchantRulesPage'
import { StocksPortfolioPage } from '@/pages/StocksPortfolioPage'
import { NetWorthPage } from '@/pages/NetWorthPage'
import { RecurringPaymentsPage } from '@/pages/RecurringPaymentsPage'
import { ReportsPage } from '@/pages/ReportsPage'
import { SettingsPage } from '@/pages/SettingsPage'
import { StatementImportPage } from '@/pages/StatementImportPage'
import { TransactionTemplatesPage } from '@/pages/TransactionTemplatesPage'
import { TransactionsPage } from '@/pages/TransactionsPage'
import { LoginPage } from '@/pages/LoginPage'
import { clearApiKey, getStoredApiKey } from '@/lib/api'

type AuthStatus = 'checking' | 'no-auth' | 'authenticated' | 'needs-login'

function AppRoutes() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<DashboardPage />} />
          <Route path="accounts" element={<AccountsPage />} />
          <Route path="transactions/templates" element={<TransactionTemplatesPage />} />
          <Route path="transactions/merchants" element={<MerchantRulesPage />} />
          <Route path="merchants" element={<MerchantRulesPage />} />
          <Route path="transactions" element={<TransactionsPage />} />
          <Route path="budget" element={<BudgetPage />} />
          <Route path="debt" element={<DebtPage />} />
          <Route
            path="credit-cards/:cardId/statements/:statementId"
            element={<CreditCardStatementPage />}
          />
          <Route path="credit-cards/statements" element={<CreditCardStatementInboxPage />} />
          <Route path="credit-cards/:cardId" element={<CreditCardDetailPage />} />
          <Route path="credit-cards" element={<CreditCardsPage />} />
          <Route path="recurring" element={<RecurringPaymentsPage />} />
          <Route path="investments/stocks" element={<StocksPortfolioPage />} />
          <Route path="investments" element={<InvestmentsPage />} />
          <Route path="net-worth" element={<NetWorthPage />} />
          <Route path="assets/:assetId" element={<AssetDetailPage />} />
          <Route path="assets" element={<AssetsPage />} />
          <Route path="construction" element={<ConstructionPage />} />
          <Route path="insurance" element={<InsurancePage />} />
          <Route path="goals" element={<GoalsPage />} />
          <Route path="home/:itemId" element={<HomeItemDetailPage />} />
          <Route path="home" element={<HomeInventoryPage />} />
          <Route path="income" element={<IncomeTaxPage />} />
          <Route path="reports" element={<ReportsPage />} />
          <Route path="journal" element={<JournalPage />} />
          <Route path="email-inbox" element={<EmailInboxPage />} />
          <Route path="statement-import" element={<StatementImportPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default function App() {
  const [authStatus, setAuthStatus] = useState<AuthStatus>('checking')

  useEffect(() => {
    let cancelled = false

    async function check() {
      try {
        const res = await fetch('/health')
        const data = await res.json() as { auth_required?: boolean }

        if (cancelled) return

        if (!data.auth_required) {
          setAuthStatus('no-auth')
          return
        }
        // Auth required — check if we have a key stored
        setAuthStatus(getStoredApiKey() ? 'authenticated' : 'needs-login')
      } catch {
        if (!cancelled) setAuthStatus('needs-login')
      }
    }

    void check()
    return () => { cancelled = true }
  }, [])

  // Listen for 401 responses from any API call
  useEffect(() => {
    function onUnauthorized() {
      clearApiKey()
      setAuthStatus('needs-login')
    }
    window.addEventListener('finance:unauthorized', onUnauthorized)
    return () => window.removeEventListener('finance:unauthorized', onUnauthorized)
  }, [])

  if (authStatus === 'checking') {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-50">
        <div className="size-6 animate-spin rounded-full border-2 border-zinc-200 border-t-emerald-600" />
      </div>
    )
  }

  if (authStatus === 'needs-login') {
    return <LoginPage onLogin={() => setAuthStatus('authenticated')} />
  }

  return <AppRoutes />
}
