// MOCK DATA — hackathon placeholder standing in for a real core-banking
// feed. There's no live account/transaction integration behind this;
// it's here purely so the app can show "Accounts with Nedcore" and
// (later) a surplus/push-notification feature can read from the same
// shape without a real data source. Swap this for a real API call
// when there's an actual core-banking feed to hook into.

export const MOCK_ACCOUNTS = [
  { id: "everyday", name: "Everyday Account", type: "Cheque account", balance: 12450.32, accountNumber: "•••• 4821" },
  { id: "savings", name: "Savings Account", type: "Savings", balance: 34200.0, accountNumber: "•••• 7734" },
  { id: "credit", name: "Credit Card", type: "Credit", balance: -3120.55, accountNumber: "•••• 9012" },
];

export function totalNedcoreBalance() {
  return MOCK_ACCOUNTS.reduce((sum, a) => sum + a.balance, 0);
}
