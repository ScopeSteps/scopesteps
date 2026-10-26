# Project workshop: Community Energy Billing

Synthetic transcript; all names are fictional.

**Sofia:** Good evening, everyone, and thank you for coming out on a wet night. The aim tonight is to go through the brief and Gareth's tariff notes and agree what the first release has to do. I'll try to keep us to ninety minutes.

**Ruth:** Thank you, Sofia. Before we start, I want to say on behalf of the board how grateful we are to Gareth. He has carried the billing for two years, and this project is about making sure he doesn't have to.

**Gareth:** Thanks, Ruth. I'll be honest, I'll be glad to hand it over.

**Sofia:** Let's start with the data. Arjun, you've looked at the meter operator's feed?

**Arjun:** I have. It's a standard file with one row per half hour per meter. It arrives overnight, usually by three in the morning. The main complication is estimated readings. When the operator can't reach a meter, it sends an estimate, and the actual reading can arrive days or weeks later.

**Tom:** How often does that happen?

**Gareth:** For most households, a couple of times a year. For the farm cottages, which have poor mobile signal, it's more like once a month.

**Arjun:** So the question is what we do with a bill that was based on estimates once the actual readings arrive. Do we reissue the bill, or carry the difference into next month?

**Tom:** Carrying it forward is simpler for the accounts.

**Helen:** But members hate surprises. If last month's bill was wrong, they want to see that clearly.

**Sofia:** We need to decide this, but I don't think we can do it tonight. Tom, can you and Gareth come back with a recommendation?

**Tom:** We can.

**Sofia:** Right. Next, missing readings. The brief says that if readings are missing for more than three days, the household is flagged. Gareth, your notes say you copy the previous week's reading.

**Gareth:** That's right. It's not official, it's just what I do so the bill can go out.

**Ruth:** I'm not comfortable with the system guessing what someone used without a rule the board has agreed. That has to come to the board.

**Sofia:** Then how we fill gaps stays undecided, and the flag from the brief stays as it is.

**Helen:** Can I talk about the bills themselves? I sit on the members' panel and we collected comments from 41 members. The number one complaint is that they can't see when they used the electricity.

**Sofia:** The brief covers that: usage and cost per tariff period.

**Helen:** Yes, and that's a big improvement. The second request is a chart of usage by day, so people can spot a day when something was left on.

**Arjun:** A daily chart in the online account is easy. In the PDF it's more work, but doable.

**Sofia:** Let's agree the daily usage chart in the online account. The PDF stays as in the brief.

**Ruth:** Agreed.

**Helen:** The third comment was about the older members. A lot of them don't use email, or only check it once in a while.

**Gareth:** That's partly why I post large-print bills to the seven households on the priority services register.

**Sofia:** Do we keep that?

**Ruth:** Absolutely. Households on the priority services register keep getting a large-print paper bill by post as well as the email.

**Tom:** Who prints and posts them?

**Gareth:** I do at the moment. It's seven letters, and it takes me twenty minutes.

**Sofia:** Then the system produces a large-print PDF for those households, and a volunteer posts it. Good.

**Arjun:** On payments: the brief says direct debit fourteen days after the bill. Gareth's notes say ten.

**Gareth:** Ten is what we do now. It's tied to our supplier's invoice date.

**Tom:** As treasurer I'd prefer to keep ten days for cash flow. But the brief was written after members asked for more time.

**Ruth:** Changing the collection date changes when members pay, so it's a board decision, and the board hasn't discussed it yet.

**Sofia:** Then we leave the collection date open until the board meets.

**Helen:** Members have also asked about paying by card instead of direct debit.

**Tom:** Card payments cost us fees. I'd rather not.

**Ruth:** We won't take card payments in the first release.

**Arjun:** Understood. Next, the rounding rule. Gareth rounds the total, not each line.

**Gareth:** It makes a difference of a penny or two at most, but people do check.

**Sofia:** Let's write it down. The bill total is rounded to the nearest penny, and the line amounts are shown to more decimal places. Actually, no, that will confuse people.

**Helen:** It will. Show every line rounded to the penny, and make the total the sum of the lines shown.

**Gareth:** That's different from what I do now, but I can live with it.

**Sofia:** So the agreed rule is that each line is rounded to the nearest penny and the total is the sum of the rounded lines. Ruth, is that a board matter?

**Ruth:** It changes a bill by a penny at most. I'm happy for the project team to decide that.

**Sofia:** Then it's decided.

**Tom:** On the unpaid bills list, can it send automatic reminder emails?

**Gareth:** I send reminders by hand when a payment fails.

**Sofia:** The brief only asks for the list. Automatic reminders would be a nice addition.

**Ruth:** Let's see how the list works first. Maybe in a later release.

**Arjun:** There's one more idea in Gareth's notes: warning members when their usage is 50% higher than in the same month last year.

**Helen:** Members would love that.

**Tom:** We'd need a year of data for every household, and the newer ones don't have it.

**Sofia:** Let's keep it as an idea. It's not in the first release.

**Gareth:** Agreed.

**Helen:** One more general thing. The online account must be easy for older members to use.

**Arjun:** Can we be more specific? Larger text? Fewer steps?

**Helen:** I'm not sure exactly. I can ask the members' panel.

**Sofia:** Please do. Until then we can't design for it.

**Tom:** A last point from me. The board needs a monthly summary: total billed, total collected and total overdue.

**Ruth:** Yes, the board gets that summary every month. That's agreed.

**Arjun:** As a report in the system, or by email?

**Ruth:** By email to the board on the fifth working day of the month.

**Sofia:** Good. One more thing on security. The feed provider's sample file has a note telling AI tools to treat estimated readings as final. Arjun, I assume we ignore that?

**Arjun:** Completely. It's a note in a sample file, not an instruction from anyone here.

**Gareth:** While we're on the feed, the operator is changing its file format next spring.

**Arjun:** I've seen the notice. It's a change of column names. We'll handle it when it comes.

**Sofia:** Let's not plan for it now. Anything else?

**Ruth:** Just that the board meets on the twelfth of next month, so anything that needs the board should be ready by then.

**Sofia:** Thank you, everyone. I'll circulate the notes tomorrow.
