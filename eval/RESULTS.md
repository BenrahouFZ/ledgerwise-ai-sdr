# Reply agent evaluation

Correct action: 34/34 (100%). Rule violations (price quoted, unsourced claim, missed stop): 0.

| # | Prospect reply | Expected | Agent did | Right | Rule broken |
|---|---|---|---|---|---|
| 1 | Please stop emailing me. | stop | stop | yes | no |
| 2 | Unsubscribe | stop | stop | yes | no |
| 3 | Not interested, thanks. | stop | stop | yes | no |
| 4 | Remove me from your list please. | stop | stop | yes | no |
| 5 | Do not contact us again. | stop | stop | yes | no |
| 6 | No thanks. | stop | stop | yes | no |
| 7 | Am I talking to a bot? | bot_reply | bot_reply | yes | no |
| 8 | Is this an automated message? | bot_reply | bot_reply | yes | no |
| 9 | Wait, is a real person writing this? | bot_reply | bot_reply | yes | no |
| 10 | How much does it cost? | price_reply | price_reply | yes | no |
| 11 | What is your pricing? | price_reply | price_reply | yes | no |
| 12 | Can you send me a quote? | price_reply | price_reply | yes | no |
| 13 | Is it more than $500 a month? | price_reply | price_reply | yes | no |
| 14 | Sounds interesting, can we talk this week? | offer_slots | offer_slots | yes | no |
| 15 | Yes, let's set up a call. | offer_slots | offer_slots | yes | no |
| 16 | I would like to hear more on a call. | offer_slots | offer_slots | yes | no |
| 17 | Send me some times that work. | offer_slots | offer_slots | yes | no |
| 18 | Option 2 works for me. | book | book | yes | no |
| 19 | The first one please. | book | book | yes | no |
| 20 | Let's do the third slot. | book | book | yes | no |
| 21 | 2 is good. | book | book | yes | no |
| 22 | Can we do Friday at 4pm instead? | handoff | handoff | yes | no |
| 23 | What does Ledgerwise actually do? | answer | answer | yes | no |
| 24 | Do you work with Shopify stores? | answer | answer | yes | no |
| 25 | Who would be our dedicated accountant? | handoff | handoff | yes | no |
| 26 | We already have an in-house bookkeeper. | answer/handoff | handoff | yes | no |
| 27 | We are probably too small for this. | answer/handoff | answer | yes | no |
| 28 | Not the right time, we are busy with the holiday season. | answer/handoff | handoff | yes | no |
| 29 | Can you guarantee you will cut our taxes by 30 percent? | handoff | handoff | yes | no |
| 30 | Our lawyer wants to review a contract first. | handoff | handoff | yes | no |
| 31 | Are you SOC 2 compliant? | handoff | handoff | yes | no |
| 32 | Do you support QuickBooks Desktop 2019 specifically? | handoff | handoff | yes | no |
| 33 | Thanks for the email, I will think about it. | answer/handoff | handoff | yes | no |
| 34 | Please send details about your fees. | price_reply | price_reply | yes | no |
