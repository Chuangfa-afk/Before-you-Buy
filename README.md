# 🚗 Before You Buy — MSRP Intelligence

### **Stop getting ripped off at dealerships.**

> _"The average American overpays $1,000–$4,000 on a car purchase. This app exists so you don't."_

🔗 **Live App → [before-you-buy.onrender.com](https://before-you-buy.onrender.com)**

---

## What Is This?

You found a car you like. The salesperson is smiling. The numbers feel... okay? But are they actually okay?

**Before You Buy** is the app you open on your phone while the salesperson "goes to check with the manager." In 30 seconds, you'll know:

- ✅ Whether the price you're being quoted is a great deal, fair, or highway robbery
- ✅ What this car will **actually cost you** over 5 years (spoiler: it's not just the sticker price)
- ✅ The **best month of the year** to buy this exact car
- ✅ What real owners say — the good, the bad, and the ugly
- ✅ Which junk fees to cross off the contract before you sign
- ✅ How to negotiate like you've done this before

No account. No subscription. No BS. Just answers.

---

## The Problem We're Solving

Car dealerships have **information asymmetry** on their side. They know:
- What the car actually cost them
- What similar cars sold for last week
- That you've been test driving for 2 hours and you're emotionally attached

You know: nothing.

**Before You Buy flips that.**

---

## How To Use It

### 1. Enter Your Car Details
Head to **[before-you-buy.onrender.com](https://before-you-buy.onrender.com)** and fill in:
- **New or Used** — toggle at the top
- **Year, Make, Model** — the exact car you're looking at
- **Your quoted price** — what the dealer told you
- **How many years** you plan to keep it (default: 5)
- **VIN** *(optional, used cars)* — for more accurate data

> 💡 Not sure yet? Hit one of the example cars (Camry, RAV4, F-150, Tesla Model 3...) to see the app in action.

### 2. Hit "Run Analysis"
The AI goes to work. In about 10–15 seconds you get a full breakdown:

#### 📊 Retail Price — Is Your Quote Fair?
A live price bar shows the **real market range** for that exact car right now — pulled from live listings. Your quoted price is plotted on that bar. You'll instantly see a verdict:

| Badge | What It Means |
|---|---|
| 🟢 **Great Deal** | You're being quoted below market. Sign it. |
| 🔵 **Fair Price** | Right around market value. Small room to negotiate. |
| 🟡 **Above Market** | Dealer's pushing it. Negotiate down. |
| 🔴 **Overpriced** | Walk away or make a lowball offer. |

#### 💸 True Cost Over 5 Years
The sticker price is just the beginning. We calculate:
- Fuel costs (based on real EPA MPG data)
- Insurance estimates
- Maintenance & repairs
- Registration & taxes
- **Resale value** — how much you get back when you sell

The big blue number is what this car will **actually** cost you. Some surprises in there.

#### 📅 Timing Advisor
Should you buy now, or wait? The app analyzes:
- **Month-by-month pricing trends** for this model
- Upcoming model year releases (new model = old model gets cheaper)
- End-of-quarter dealer pressure windows
- Holiday sales events

The bar chart shows expected price by month. Green = cheapest. Red = most expensive.

#### ⭐ Owner Reviews & Safety
Real talk from real owners — pulled from Reddit discussions and curated review data:
- **Pros** from people who own this car
- **Cons** from people who own this car (the honest ones)
- **Sentiment score** out of 5
- **NHTSA safety data** — recalls, complaints, crash ratings

#### 🚩 Gotchas & Junk Fees
Dealers love adding line items at signing. We'll flag:
- Dealer add-ons you didn't ask for
- Inflated documentation fees
- Unnecessary protection packages
- Finance office upsells

Cross these off before you sign. Every single one is negotiable.

#### 💬 Negotiation Tips
Specific to the car you're buying. Not generic advice — actual talking points you can use at the table.

---

### 3. Ask the AI Anything
Hit **"Ask AI"** to open the chat panel. Ask it anything:

> _"Should I buy this or wait for the 2026 model?"_

> _"What's a fair out-the-door price for this RAV4?"_

> _"What are the most common problems with this car after 60k miles?"_

> _"They're offering me 2.9% financing — is that good?"_

The AI has full context of your car and the analysis results. It's like texting a car-savvy friend who happens to know everything.

---

## Real Scenarios Where This Saves You Money

**Scenario 1: The Classic Overprice**
> You're looking at a used 2023 Toyota Camry for $31,000. BYB shows the market range is $26,000–$29,500. You just saved yourself $2,500 in negotiating power before you said a word.

**Scenario 2: The Timing Play**
> It's August. BYB shows that October is historically the cheapest month for this model (new model year arrives, dealers clear inventory). You wait 8 weeks and save $1,800.

**Scenario 3: The Junk Fee Ambush**
> You're at signing. The F&I manager slides over a contract with $3,200 in add-ons. BYB already warned you about "paint protection packages" and "nitrogen tire fill." You cross them off. They fold immediately.

---

## Tech Stack

Built for speed and accuracy — not to impress engineers, but to actually help people.

| Layer | Technology |
|---|---|
| Backend | Python + Flask |
| AI Analysis | Groq (Llama 3.3 70B) / Gemini / OpenAI |
| Live Market Data | Auto.dev API (real listings) |
| Fuel Economy | EPA FuelEconomy.gov API |
| Safety Data | NHTSA API |
| Frontend | Vanilla JS + CSS (no framework needed) |
| Hosting | Render |

---

## Run It Locally

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/before-you-buy.git
cd before-you-buy

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env and add your API keys
```

You'll need free API keys from:
- **[Auto.dev](https://www.auto.dev)** — live vehicle pricing data
- **[Groq](https://console.groq.com)** — fast AI inference (free tier is generous)

```bash
# Start the app
python app.py

# Open http://localhost:5001
```

---

## Environment Variables

```env
AUTO_DEV_API_KEY=your_key_here       # Live market pricing
GROQ_API_KEY=your_key_here           # AI analysis (primary)
GEMINI_API_KEY=your_key_here         # AI fallback (optional)
OPENAI_API_KEY=your_key_here         # AI fallback (optional)
```

---

## Contributing

Found a bug? Have a feature idea? PRs welcome.

Some things that would make this even better:
- [ ] More makes/models in the price database
- [ ] Lease vs buy calculator
- [ ] CPO (Certified Pre-Owned) premium analysis
- [ ] "Compare two cars" mode
- [ ] Mobile app

---

## Disclaimer

This app provides market data and AI-generated analysis for **informational purposes only**. Prices vary by region, trim level, and market conditions. Always verify with multiple sources before making a purchase decision. We're not responsible if the dealer is just really charming.

---

<div align="center">

**Made with ☕ and mild road rage**

[Live App](https://before-you-buy.onrender.com) · [Report a Bug](https://github.com/Chuangfa-afk/before-you-buy/issues) · [Request a Feature](https://github.com/Chuangfa-afk/before-you-buy/issues)

_Go get that deal. 🚗💨_

</div>
