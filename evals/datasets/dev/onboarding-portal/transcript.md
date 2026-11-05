# Discovery workshop, Welcome new starter portal

Synthetic transcript; all names are fictional. Recorded and transcribed by Teams.

[00:00:02] Hannah: Hi everyone, give it a second for people to join. Ben, how was Lisbon?

[00:00:10] Ben: Amazing, thanks. Thirty degrees every day. I ate my body weight in custard tarts and came back to four hundred emails, so, balance.

[00:00:22] Sophie: Did you go to the one by the tram stop? The famous one with the queue?

[00:00:31] Ben: Twice. The queue was forty minutes the second time. Worth it.

[00:00:38] Joel: I went to Lisbon on my stag do. I remember almost none of it, which tells you something.

[00:00:48] Hannah: Let's not go there.

[00:00:52] Felix: Sorry, my cat's just walked across the keyboard. If I send anything weird in the chat, it's her.

[00:01:02] Amira: My dog does that with the mute button. He's got me unmuted in a board meeting before.

[00:01:12] Felix: That's a nightmare. She's sat on the warm bit of the laptop now. I'm typing round her.

[00:01:22] Hannah: Ha. Okay, I think we're all here. Thanks for making the time. So this is the first proper workshop for Welcome. The aim today is to agree what a new starter does in the portal before their first day, and what happens behind the scenes, so Felix's team can plan the build for September. Joel, can you start us off with what goes wrong today?

[00:01:52] Joel: Before I do, can I give a bit of context on volumes? Because I think it matters for how we design this.

[00:02:04] Hannah: Go on.

[00:02:08] Joel: So it's about three hundred starters a year, but it's not spread evenly. September and January are huge, because of the graduate intake and the claims recruitment drive. Last September we had sixty-two people start in three weeks. My team is four people. So anything that's manual at the moment gets crushed in those months.

[00:02:33] Ben: And September is when my team is busiest too, because of the summer claims backlog.

[00:02:42] Hannah: That's why I want the first release live for September. If it slips to October we've missed the worst month.

[00:02:53] Joel: Yeah. So, today, the offer's accepted, and then the new starter gets this monster email from us with the contract and, I think it's eight attachments now. Personal details form, bank details form, the tax starter checklist, three policies to read and sign, the equipment form, the emergency contact form. They print them, or they don't, and half of them turn up on day one with nothing. Then we chase.

[00:03:25] Sophie: And the ones who do bring them, the forms are often out of date. We changed the bank form two years ago and people still turn up with the old one, because a manager saved a copy on their desktop in twenty eighteen.

[00:03:45] Joel: The emergency contact form is the worst. It asks for a fax number. A fax number.

[00:03:54] Amira: Nobody has a fax number.

[00:03:58] Joel: Kemi in claims put her nan's.

[00:04:03] Hannah: Okay, I think we've established the forms are bad. What I'd like to understand is the order things need to happen in.

[00:04:15] Joel: The order is basically: offer accepted, contract signed, then everything else. And the everything else can happen in any order, as long as it's done before day one.

[00:04:29] Sophie: And from payroll's side, bank details on paper are the worst thing. I'm typing sort codes from photos of handwriting. We had two people paid into the wrong account last year.

[00:04:44] Hannah: Wrong account how?

[00:04:48] Sophie: Typo in the account number, my typo, and the other one the sort code was from an old bank. Both of them got their first salary late. One of them had rent due. It was awful.

[00:05:05] Felix: If they type it themselves into the portal, the payroll interface checks the sort code exists. It won't catch everything, but it'll catch an old bank.

[00:05:18] Sophie: That alone would save me hours.

[00:05:23] Hannah: Right. So the core of it, I think, is the starter fills in their personal details, their emergency contact, their bank and tax details in the portal before day one, and the bank and tax details go to payroll without anyone retyping them. Does that match what everyone's got in their head?

[00:05:47] Sophie: Yes. As long as they go straight into payroll. I don't want them sat in some other system.

[00:05:57] Amira: That's my point as well, from security. The bank details shouldn't live in the portal. The portal collects them and hands them to payroll, and then they're gone from the portal. Otherwise we've got two places to protect instead of one.

[00:06:17] Felix: Just so everyone's clear what that means in practice. The starter fills in the form, presses submit, and the portal sends it to payroll over the interface. The portal keeps a note that bank details were submitted and when, but not the details themselves.

[00:06:38] Sophie: So if they ring me and say "did you get my bank details", I can see they submitted them?

[00:06:48] Felix: You'll see them in payroll, and the portal shows they were sent. Yes.

[00:06:56] Sophie: Good. That's the question I get most in September.

[00:07:02] Felix: That's doable. We pass them through to the payroll interface and don't store them on our side.

[00:07:12] Hannah: Good, let's make that a rule then. Bank and tax details go straight to payroll and aren't kept in the portal.

[00:07:23] Amira: Thank you. I'll write that into the security review as a required control so it doesn't get lost.

[00:07:33] Joel: Does the same go for the tax checklist? It's got National Insurance numbers on it.

[00:07:42] Hannah: Bank and tax together, I said. Same rule.

[00:07:48] Joel: Great, just checking.

[00:07:52] Joel: The other big one is right to work. We have to see the original passport or the share code on day one. That's the law, we can't just take a photo.

[00:08:07] Ben: Is that new? I thought you could do it online now.

[00:08:14] Joel: You can for some people, with a share code, if they've got one. For British and Irish citizens it's still the original passport, or a few other documents. It's complicated. There's a whole flowchart.

[00:08:31] Amira: And whoever does the check signs to say they've seen it. There's a fine if we get it wrong.

[00:08:41] Joel: A big fine. That's why I'm twitchy about it.

[00:08:47] Ben: Can they upload it in advance, though? So at least we know before they turn up that it's the right document?

[00:08:58] Joel: Upload in advance, yes, so we can check it's the right type of document. But someone in HR still checks the original in person on day one and ticks it off.

[00:09:13] Ben: What happens if they forget their passport on day one? It happens.

[00:09:20] Joel: Then they can't start work until we've seen it. They can come in, but they can't do any actual work. Legally.

[00:09:31] Ben: That's harsh.

[00:09:35] Joel: That's the law. That's why the upload in advance helps, we can remind them the day before what to bring.

[00:09:46] Hannah: Okay. So the starter uploads their right to work document before day one, and HR still checks the original in person on their first day and records that it's done.

[00:10:01] Amira: And those images get deleted after the check. I'll put that in my review, but just flagging it now.

[00:10:11] Joel: Hmm, we've always kept a copy for audit. The Home Office can ask to see it.

[00:10:20] Amira: Then we need to talk about that properly, because a portal full of passport scans is exactly what gets stolen.

[00:10:31] Joel: I get that, I really do. But if the Home Office turn up and ask for a copy, and we haven't got one, that's on me.

[00:10:44] Amira: And if someone breaks into the portal and takes three hundred passports, that's on me.

[00:10:53] Felix: Can I just say, technically either is fine. Keeping them, deleting them, deleting after a period. It's one setting. The question is which one.

[00:11:05] Hannah: Which is why I'm not deciding it in five minutes.

[00:11:12] Hannah: Let's note that one and come back to it. I don't want to decide it in five minutes.

[00:11:22] Joel: Policies next. Code of conduct, IT security and data protection. At the minute they sign a printed page saying they've read them, which, let's be honest, nobody has.

[00:11:36] Amira: The IT security policy is twenty-three pages. I wrote it and I'm not sure I've read it all.

[00:11:46] Joel: The data protection one is fourteen. The code of conduct is the short one, eight pages.

[00:11:55] Ben: Could we have a short version? Like a summary page at the top?

[00:12:03] Amira: There's a one-page summary of mine already. I can make sure that's shown first.

[00:12:11] Hannah: That's a nice idea, but let's not make it a requirement of the portal. The policies are the policies. If the owners want to add summaries, they can.

[00:12:25] Felix: We can show each policy in the portal and have them confirm they've read it, with the date and time recorded.

[00:12:36] Hannah: Yes. The three policies, read and acknowledged in the portal, with the date and time kept.

[00:12:45] Felix: I had an idea here, actually. What if we turned the policies into a little welcome quiz? Badges, a progress bar, "you're eighty percent ready for day one". Makes it a bit more fun.

[00:13:02] Joel: For the data protection policy? I'm not sure badges are the vibe.

[00:13:09] Hannah: I like the progress bar. Badges I'm less sure about. Let's not commit to the quiz for September. Keep it as an idea.

[00:13:21] Felix: The progress bar is easy, by the way. It's basically counting how many forms are done.

[00:13:30] Sophie: I like that. People like seeing they're nearly finished.

[00:13:36] Felix: Fair enough.

[00:13:40] Ben: Can I do the manager bit? Because this is the bit I actually care about. When someone joins my team I've got a list in my head. Desk, buddy, first week plan, invite them to the team meeting, get them on the claims training. And every time I forget one. I'd love the portal to give me a checklist.

[00:14:07] Ben: And the system access, actually. My lot need access to the claims system, the phone system and the knowledge base. Three different requests, three different teams.

[00:14:20] Amira: The claims system and phone system access come with the role. If the manager picks the right role when the offer's made, it's set up automatically. The knowledge base is separate.

[00:14:35] Ben: The knowledge base is always the one that's missing. Every time.

[00:14:42] Felix: I can put "request knowledge base access" on the claims checklist, with a link.

[00:14:50] Ben: Perfect.

[00:14:54] Hannah: A checklist for the hiring manager, with the things they need to do before and during the first week.

[00:15:04] Ben: And remind me. If it's three days before they start and I haven't done the desk, nag me.

[00:15:14] Joel: Can you nag me too? If the right to work document hasn't been uploaded by the week before?

[00:15:24] Felix: Reminders to HR as well, yes, same mechanism.

[00:15:30] Hannah: Fine, reminders to whoever owns the task.

[00:15:35] Felix: Reminders by email are easy.

[00:15:39] Hannah: Okay, checklist and email reminders for the manager.

[00:15:45] Ben: Oh, and while I'm here, between us, my team lead in claims is leaving at the end of next month, she's handed her notice in but it's not announced yet. So I'll be the one onboarding everyone for a bit. Don't say anything.

[00:16:05] Hannah: Thanks Ben. Let's keep that out of the notes.

[00:16:11] Ben: Sorry. I just wanted you to know why I might be slow on some of the checklists for a bit.

[00:16:22] Hannah: Understood. Thank you.

[00:16:26] Amira: IT side. The laptop and the accounts. The reason starters don't have a laptop is we hear about them too late. We need ten working days to get a laptop built and shipped.

[00:16:42] Hannah: Why ten? Just out of interest.

[00:16:47] Amira: Ordering, imaging, encryption, the security software, testing, then the courier. And in September the courier takes longer because every company in the country is doing the same thing.

[00:17:01] Felix: Do they go to the starter's home or the office?

[00:17:08] Amira: The office. We don't post laptops to homes before people are employees. If it goes missing, it's a nightmare.

[00:17:18] Hannah: So if the IT request was raised automatically the moment the offer's accepted, that would solve most of it?

[00:17:28] Amira: Most of it, yes. The account and the laptop request get created automatically when the offer's accepted, with the start date and the team. Then it's on us.

[00:17:42] Amira: Today the manager emails us. Some managers email a week before. Some email the day before. One manager emailed us on the starter's first day, from the starter's phone.

[00:17:56] Ben: Not me.

[00:18:00] Amira: I didn't say it was you.

[00:18:05] Ben: It was me once.

[00:18:09] Ben: What about when someone starts in a week, though? We had a guy last month who could start on the Monday, so we said yes.

[00:18:22] Amira: Then they won't have a laptop. I can't build one in three days without stealing it from someone else.

[00:18:32] Hannah: So what do we do for those? Loan laptops? Push the start date?

[00:18:40] Amira: I don't know, honestly. That's a policy call, not an IT one.

[00:18:47] Joel: We used to have a few spare laptops, didn't we? In the cupboard by the lifts.

[00:18:56] Amira: We had three. Two got stolen from the cupboard by the lifts, which is why we don't keep laptops in the cupboard by the lifts anymore.

[00:19:09] Hannah: Okay, that's open. What happens when someone's start date is less than ten working days after they accept.

[00:19:19] Ben: How often is that, out of interest? Short notice starts?

[00:19:26] Joel: Maybe one in ten? More in claims, because people come from agencies and can start straight away.

[00:19:36] Hannah: So in September that could be six or seven people. Not nothing.

[00:19:43] Joel: Last thing from me. Diversity monitoring. We're supposed to be collecting the equal opportunities questions, ethnicity, disability and so on, and at the minute it's a paper form that most people don't return.

[00:19:59] Amira: That's special category data. If we're collecting it, it needs a lot of care.

[00:20:07] Joel: We have to report the numbers every year though. Gender pay gap, and the diversity report the board asked for. At the moment we're guessing for a third of people.

[00:20:22] Hannah: I know. I want to do it properly, which is why I want legal to tell us how.

[00:20:32] Hannah: I need to check with legal what we're allowed to do there before we put it anywhere. Park it for now.

[00:20:43] Joel: Sure. Oh, and on that, I'll be honest, we've had a real issue. Leon, who started in claims last month, told us he has epilepsy and asked for an adjustment to his screen setup, and we lost the form. He had to tell three different people. That's partly why I care about this.

[00:21:07] Hannah: Joel, that's really important, but please let's not use names. The point is that starters should be able to ask for adjustments in one place. Let's come back to how that works in the design review.

[00:21:24] Joel: Yes, sorry. Good point.

[00:21:28] Felix: For what it's worth, the adjustments thing could be a simple form. What they need, who can see it. We can design it for the review.

[00:21:41] Hannah: Yes, bring something to the review and we'll decide who sees it then.

[00:21:49] Felix: Can I check scope? Contracts. Are we doing contract signing in the portal?

[00:21:57] Hannah: No. Contracts stay in the e-signature tool, it works and legal like it. The portal just links to it.

[00:22:07] Felix: So after they sign the contract in the e-signature tool, they get sent to the portal automatically?

[00:22:17] Joel: That would be lovely. At the moment they get a separate email from us, sometimes days later.

[00:22:27] Felix: The e-signature tool can call a link when the contract's completed. I'll look into it.

[00:22:36] Hannah: Look into it, but don't promise it for September until you know it works.

[00:22:44] Ben: And probation reviews? Could the portal track those too? Three month review, six month review.

[00:22:53] Hannah: Not in the first release. Probation stays in the HR system as it is. Let's get the first month right before we take on more.

[00:23:06] Ben: Fair. It's just the reminders would be so useful there.

[00:23:13] Hannah: I know. Next year, maybe.

[00:23:17] Felix: And contractors and temps? Do they get the portal?

[00:23:23] Hannah: Good question. The brief says permanent employees. Temps come through the agency. Contractors, I'm not sure. Let me think about that one.

[00:23:35] Ben: I've got two contractors starting in October, that's why I'm asking.

[00:23:42] Felix: They'd need the laptop and the accounts as well, so at least the IT bit would be useful for them.

[00:23:53] Hannah: Noted. I'll come back to it.

[00:23:58] Joel: Before we finish, does anyone know if the office move is still happening in October? Because I've got a starter asking which building to go to.

[00:24:11] Hannah: Still October as far as I know, but don't quote me. Right, let me sum up. Personal details, emergency contact, bank and tax details in the portal before day one, bank and tax straight to payroll and not stored. Right to work uploaded in advance, original checked in person on day one, and what we keep is open. Three policies acknowledged with a timestamp. Manager checklist with reminders. IT account and laptop request raised automatically on acceptance, short-notice starters open. Diversity monitoring parked until legal comes back. Contracts stay in e-signature. Probation stays in the HR system. Contractors open. The quiz is an idea, not a commitment.

[00:24:58] Sophie: Is it still the new building on Harbour Street?

[00:25:04] Hannah: Still Harbour Street. And there's parking, before anyone asks.

[00:25:10] Ben: Is there? Proper parking?

[00:25:14] Hannah: I've been told there's parking. Whether there's enough is another question.

[00:25:21] Felix: Can I share a rough design before the review? Just to get early reactions?

[00:25:29] Hannah: Yes, send it to everyone on this call. Comments by the end of next week.

[00:25:38] Amira: And copy me on anything that touches personal data, please. Which is all of it, I suppose.

[00:25:48] Hannah: Before we finish, can we talk about how we'd know this has worked? Because I'll be asked in March whether it was worth it.

[00:26:00] Joel: The forms. If ninety percent of starters have done everything before day one, that's a huge win. Today it's maybe forty percent.

[00:26:12] Sophie: Payroll errors. Zero wrong accounts would be nice. Last year was two, and the year before that was four.

[00:26:22] Amira: Laptops on day one. Today about a third of starters don't have one. I'd like that under one in twenty.

[00:26:33] Ben: And the starters themselves. Do they feel welcome? We do a first-month survey already, we could add a question.

[00:26:43] Hannah: Good. Joel, can you look at the survey?

[00:26:49] Joel: I'll add two questions. One about the portal, one about the first day.

[00:26:57] Felix: The portal can tell you the first three numbers automatically, by the way. How many finished before day one, how many bank details went through, how many short-notice laptops were flagged.

[00:27:12] Hannah: Even better. Then we don't have to count by hand.

[00:27:19] Amira: As long as the numbers are anonymous. No list of names of who didn't finish their forms.

[00:27:29] Hannah: Numbers only for the report. HR can see their own starters' progress, obviously, that's their job.

[00:27:38] Ben: One more thing from me, and then I'll be quiet. Can the starter see the manager's name and a photo? I always think it's nice to know who you're meeting.

[00:27:53] Felix: The manager's name is on the welcome page already, from the offer. A photo would need the manager to upload one.

[00:28:04] Ben: I'd upload one.

[00:28:08] Hannah: Let's leave photos of managers out. Some people really don't want their photo anywhere. The name is enough.

[00:28:18] Ben: Fair enough.

[00:28:22] Sophie: And can I check the timing? If the portal opens the moment the offer's accepted, and the start date is three months away, will people forget about it?

[00:28:36] Joel: They might. Three months is a long time.

[00:28:42] Felix: The reminders could go to the starter too, not just the manager. A nudge four weeks before, one week before.

[00:28:53] Hannah: Yes, reminders to the starter as well. That's sensible.

[00:28:59] Joel: I'll write the reminder wording. Friendly, not "you have failed to complete".

[00:29:06] Amira: Please don't put links in reminder emails that look like phishing. We spend all year telling people not to click links in emails.

[00:29:18] Felix: The emails come from our domain and say exactly what they are. And they can always go to the portal directly instead of clicking.

[00:29:30] Amira: Okay.

[00:29:34] Hannah: Right. Anything else, or shall I sum up?

[00:29:40] Ben: Just to say thank you. This is the first HR project I've been asked into before it was finished.

[00:29:50] Hannah: Ha. That's very kind, and slightly damning. Let me sum up.

[00:29:57] Felix: Which is all of it, yes.

[00:30:02] Felix: Got all of that. I'll turn it into a design for the review in two weeks.

[00:30:11] Hannah: Thanks everyone.
