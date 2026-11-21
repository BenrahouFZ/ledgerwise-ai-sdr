# How I worked

Project: AI SDR platform for Ledgerwise (US bookkeeping firm for e-commerce brands).
Live site: https://ledgerwise-ai-sdr-ird8.onrender.com 
Code: https://github.com/BenrahouFZ/ledgerwise-ai-sdr

**Important:** this platform runs in demo mode. Approved emails go to an outbox inside the app and nothing is sent to real companies. Prospect replies are simulated with a "simulate reply" box. Calls are booked for real in a Cal.com demo calendar, and the invitation goes to a plus-address of my demo email.

---

## 1. Tools I used for each step, and why

I built everything with **Claude (the regular chat on claude.ai)**. I pasted the Unscale brief, asked what the best approach was, and followed the stack it suggested. I know Render and Supabase from before, which made me comfortable agreeing with it. I reviewed and ran every file myself.

## Technology Stack & System Components

01. Research — Tavily
Search and page reading. Free tier. It returns page text, so the code can check that a quote really appears in the page.

02. Qualification — Gemini + My Code
Gemini (free tier) reads the sources and gives each criterion a value and an exact quote. My code checks the quote and computes the score.

The AI never gives the score. Every point comes from a verified quote, so every point is explainable.

03. Email Writing — Gemini
Uses only the stored, sourced facts. The facts used are saved with each draft and shown to the reviewer.

04. Replies — Rules in Code + Gemini
Rules in code first (stop words, "are you a bot?"), then Gemini to classify the intent.

The rules that must never fail do not depend on the AI.

05. Booking Calls — Cal.com API v2
Free, real free slots, and real bookings.

06. Platform — FastAPI + HTML/JS
Python and one HTML/JS page with no build step. Simple to read, simple to deploy, and I can explain every line.

07. Database — Supabase (Postgres)
I already knew it, and the free tier is enough.

08. Hosting — Render + UptimeRobot
Render (free) plus UptimeRobot pinging `/stats`. I already knew Render. The free plan sleeps when idle, so the ping keeps it awake.

09. AI Coding Tool — Claude (claude.ai chat)

**Tool I considered and dropped:** Qwen as the AI model. I dropped it after asking Claude for the best approach. The setup it suggested (Gemini free tier, Tavily, Supabase, Render) convinced me and used tools I already knew. 

The AI provider is one setting in `app/llm.py`, so Gemini, Groq or Claude can be swapped with one environment variable.

## 2. My plan, and how it changed

**First plan:** one pipeline: find companies, enrich and qualify them, write the first email, handle replies, book calls, and a simple screen for the sales team.

**What changed** (bugs and unsatisfying results pushed these changes):
- The first search results included companies that did not fit: large or public brands, restaurants, a sports team, and results that were not company names.
- Some matched the wrong website. I only accept a website whose domain matches the company name.
- Some companies had no proof of a US location. I made a verified US location mandatory, and added the `recheck` and `requalify` commands.
- I did not have enough small brands, so I added a second list of queries aimed at small brands, and a file of extra queries.
- Result: 124 companies researched. 70 were rejected by the rules, and 54 are in the pipeline (33 qualified with no email yet, 13 with a draft, 5 contacted, 3 with a booked call).
- I kept the 70 rejected companies in the database instead of deleting them. The sales team can open the "Rejected" filter, see the reason or score for each one, and click "Mark as qualified" if they disagree. This lets them check my qualification rules and correct them by hand.


## 3. Rules and context I gave my AI tool

The only context was the **Unscale brief** (the client, the five rules and the job). I turned each rule into code in `app/safety.py` and `app/agent.py`, so it does not depend only on a prompt:

1. **Never quote a price:** a price pattern blocks any message. Pricing questions always get a fixed answer that suggests a call.
2. **Never claim anything untrue:** a fact needs a verified quote and a source link. Any number in a message must exist in the sources.
3. **Stop means stop:** stop words add the company to a do-not-contact list, nothing is sent, and every send path checks the list.
4. **Honest about being a bot:** a fixed honest answer.
5. **Unsure goes to a human:** low confidence, a rule-breaking answer, or a topic outside the knowledge file becomes a draft for a person.

## 4. Where the AI got something wrong, and how I noticed

1. **The agent invented a claim (evaluation case 25).** A prospect asked "Who would be our dedicated accountant?" and the agent answered that the account would be handled by an experienced team of bookkeepers with consistent support. Nothing in the knowledge file says that. I noticed because my evaluation expected a handoff and the agent answered (33/34). The checks only catch numbers and prices, so they could not catch an invented description. I fixed the prompt: questions about people, delivery, security and guarantees now go to a human.
2. **My evaluation was wrong, not the agent (case 27).** It flagged the numbers "1 to 10 million" and "5 to 50", which come from the knowledge file. The evaluation compared against a smaller text than the real agent does. I fixed the evaluation so both use the same sources.
3. **A rejected first email left the company stuck.** The company stayed "email drafted" and the team would not be able to write a new email. I found it and told claude to review the code and fix that part. He fixed it according to my request so a rejected email returns the company to "qualified", and added a test.

## 5. How I checked that the agent's answers are right

- **34 test replies** (`eval/replies.json`, results in `eval/RESULTS.md`): stop requests, bot questions, price questions, call requests, slot picks, objections, and questions the agent must not answer (legal, security, guarantees).
- **Final run: 34/34 correct actions, 0 rule violations.**{'email_drafted': 13, 'rejected': 70, 'qualified': 33, 'booked': 3, 'contacted': 5} total: 124
- **19 automatic tests** run without internet or keys (rules, stop, booking, human takeover, email review).
- **Booking tested live:**  bookings made on the live site, visible in the Calls booked tab and in Cal.com.
- **Limits:** the evaluation only tests the decision step, not the database or Cal.com. The stop-word rule also triggers on words like "stop" inside other sentences. It fails safe, but it could lose a lead. I wrote the test cases myself, so real replies will be messier.

## 6. What it costs to run, and what I would do next

Cost today: $0 Everything is on free tiers (Gemini, Tavily, Supabase, Render, Cal.com, UptimeRobot). [i have consumed 449 / 1,000 credits of tavily free tier ]

Work per lead : researching one company takes one AI call and up to five Tavily calls. A first email takes one AI call. A reply takes zero AI calls for stop and bot questions, and one otherwise. A booking takes two Cal.com calls. The code waits 4 seconds between AI calls to stay under the free rate limit.

With more time, I would:
- Send and receive real email, with an unsubscribe link and compliance checks, instead of the outbox and simulated replies.
- Find contact email addresses. Today I find a contact name and role, but not an address.
- Test the reply agent on real replies and on a set of cases I did not tune on.
- Make the reply agent able to answer more questions related to Ledgerwise's goal. This means a bigger knowledge file (services, process, FAQs) approved by the client, so fewer threads go to a human, while anything outside it still goes to a human.
- Improve the interface: for example filters and sorting on every screen, bulk approve for emails, and better mobile layout.
- Find companies automatically. Research would run on a schedule and add new companies as soon as they post a trigger, such as a finance job, a funding announcement or a new sales channel.
- Run research on a schedule instead of from my laptop, and add a separate login for each sales person.
- Check at least a sample of qualified companies by hand to measure how often a quote and its source are correct.

## 7. Time spent

About 15 hours in total, spread over several sessions because I had other commitments during the 72 hours and could not work continuously. I focused on a working, deployed platform with the five client rules enforced in code, and on testing it. Section 6 lists what I would improve with more time.