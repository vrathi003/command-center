import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import { AppShell } from '@/components/layout/AppShell'
import { AccountsPage } from '@/pages/AccountsPage'
import { AssetDetailPage } from '@/pages/AssetDetailPage'
import { AssetsPage } from '@/pages/AssetsPage'
import { BudgetPage } from '@/pages/BudgetPage'
import { ConstructionPage } from '@/pages/ConstructionPage'
import { CreditCardDetailPage } from '@/pages/CreditCardDetailPage'
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
import { StocksPortfolioPage } from '@/pages/StocksPortfolioPage'
import { NetWorthPage } from '@/pages/NetWorthPage'
import { RecurringPaymentsPage } from '@/pages/RecurringPaymentsPage'
import { ReportsPage } from '@/pages/ReportsPage'
import { SettingsPage } from '@/pages/SettingsPage'
import { TransactionTemplatesPage } from '@/pages/TransactionTemplatesPage'
import { TransactionsPage } from '@/pages/TransactionsPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<DashboardPage />} />
          <Route path="accounts" element={<AccountsPage />} />
          <Route path="transactions/templates" element={<TransactionTemplatesPage />} />
          <Route path="transactions" element={<TransactionsPage />} />
          <Route path="budget" element={<BudgetPage />} />
          <Route path="debt" element={<DebtPage />} />
          <Route
            path="credit-cards/:cardId/statements/:statementId"
            element={<CreditCardStatementPage />}
          />
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
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
