const translations = {
    en: {
        "nav-dashboard": "Dashboard",
        "nav-send": "Send Money",
        "nav-pay": "Pay Bills",
        "nav-history": "History",
        "nav-logout": "Logout",
        "sidebar-protected-wallet": "Protected Wallet",
        "sidebar-crypto-info": "Transaction values remain encrypted at rest.",
        "sidebar-menu": "Menu",
        "sidebar-security": "Security",
        "sidebar-aes-active": "AES-256-GCM Active",
        "sidebar-session-encrypted": "Session Secured",
        "btn-signin": "Sign in",
        "btn-open-account": "Open account",
        "btn-login": "Login to Account",
        "btn-register": "Create Secure Account",
        "btn-verify": "Verify OTP",
        "label-email": "Email Address",
        "label-password": "Password",
        "label-fullname": "Full Name",
        "label-phone": "Phone Number",
        "platform": "Platform",
        "security": "Security",
        "welcome-back": "Welcome back",
        "confirm-transfer": "Send TZS {amount} to account {to}?\n\nThis action cannot be undone.",
        "confirm-bill": "Pay TZS {amount} to {biller}?\n\nThis action cannot be undone.",
        "error-required": "This field is required",
        "alert-logged-out": "You have been logged out.",
        "lang-en": "English",
        "lang-sw": "Kiswahili",

        "title-dashboard": "Dashboard",
        "welcome-back": "Welcome back, {name}",
        "btn-send-money": "Send Money",
        "nav-send": "Send Money",
        "nav-pay": "Pay Bills",
        "nav-history": "History",
        "sidebar-security": "Security",
        "platform": "Platform",
        "security": "Security",

        "payment-flow": "Payment Flow",
        "recent-transactions": "Recent Transactions",
        "view-all": "View all →",
        "no-transactions": "No transactions yet",
        "send-first-payment": "Send your first payment →",

        "transfer-details": "Transfer Details",
        "transfer-security": "Transfer Security",
        "send-money": "Send Money",
        "pay-bills": "Pay Bills",
        "transaction-history": "Transaction History"
    },
    sw: {
        "nav-dashboard": "Dashibodi",
        "nav-send": "Tuma Pesa",
        "nav-pay": "Lipia Bili",
        "nav-history": "Historia",
        "nav-logout": "Ondoka",
        "sidebar-protected-wallet": "Mkoba uliolindwa",
        "sidebar-crypto-info": "Thamani za miamala zimefichwa kikamilifu.",
        "sidebar-menu": "Menyu",
        "sidebar-security": "Usalama",
        "sidebar-aes-active": "AES-256-GCM Imekubaliwa",
        "sidebar-session-encrypted": "Kipindi Kimelindwa",
        "btn-signin": "Ingia",
        "btn-open-account": "Fungua akaunti",
        "btn-login": "Ingia kwenye Akaunti",
        "btn-register": "Tengeneza Akaunti Salama",
        "btn-verify": "Thibitisha OTP",
        "label-email": "Barua Pepe",
        "label-password": "Nywila",
        "label-fullname": "Jina Kamili",
        "label-phone": "Namba ya Simu",
        "platform": "Jukwaa",
        "security": "Usalama",
        "welcome-back": "Karibu tena",
        "confirm-transfer": "Tuma TZS {amount} kwenda akaunti {to}?\n\nKitendo hiki hakiwezi kubatilishwa.",
        "confirm-bill": "Lipia TZS {amount} kwenda {biller}?\n\nKitendo hiki hakiwezi kubatilishwa.",
        "error-required": "Sehemu hii inahitajika",
        "alert-logged-out": "Umetolewa kwenye mfumo.",
        "lang-en": "Kiingereza",
        "lang-sw": "Kiswahili"
    }
};

/**
 * Helper to get a translated string by key
 */
function i18n(key, params = {}) {
    const lang = localStorage.getItem('preferredLanguage') || 'en';
    let text = translations[lang][key] || key;
    
    // Replace placeholders like {amount}
    Object.keys(params).forEach(p => {
        text = text.replace(new RegExp(`\\{${p}\\}`, 'g'), params[p]);
    });
    return text;
}

/**
 * Updates all DOM elements with [data-i18n] attribute
 */
function updatePageLanguage() {
    const lang = localStorage.getItem('preferredLanguage') || 'en';
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        if (translations[lang][key]) {
            if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
                el.placeholder = translations[lang][key];
            } else {
                el.innerText = translations[lang][key];
            }
        }
    });
    document.documentElement.lang = lang;
}