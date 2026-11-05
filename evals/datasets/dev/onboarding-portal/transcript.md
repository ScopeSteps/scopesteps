# Discovery workshop, Welcome new starter portal

Synthetic transcript; all names are fictional. Recorded and transcribed by Teams.

[00:00:02] Hannah: Hi everyone, give it a second for people to join. Ben, how was Lisbon?

[00:00:07] Ben: Amazing, thanks. Thirty degrees every day. I ate my body weight in custard tarts and came back to four hundred emails, so, balance.

[00:00:15] Felix: Sorry, my cat's just walked across the keyboard. If I send anything weird in the chat, it's her.

[00:00:20] Hannah: Ha. Okay, I think we're all here. Thanks for making the time. So this is the first proper workshop for Welcome. The aim today is to agree what a new starter does in the portal before their first day, and what happens behind the scenes, so Felix's team can plan the build for September. Joel, can you start us off with what goes wrong today?

[00:00:41] Joel: Yeah. So, today, the offer's accepted, and then the new starter gets this monster email from us with the contract and, I think it's eight attachments now. Personal details form, bank details form, the tax starter checklist, three policies to read and sign, the equipment form, the emergency contact form. They print them, or they don't, and half of them turn up on day one with nothing. Then we chase.

[00:01:04] Sophie: And from payroll's side, bank details on paper are the worst thing. I'm typing sort codes from photos of handwriting. We had two people paid into the wrong account last year.

[00:01:12] Hannah: Right. So the core of it, I think, is the starter fills in their personal details, their emergency contact, their bank and tax details in the portal before day one, and the bank and tax details go to payroll without anyone retyping them. Does that match what everyone's got in their head?

[00:01:28] Sophie: Yes. As long as they go straight into payroll. I don't want them sat in some other system.

[00:01:33] Amira: That's my point as well, from security. The bank details shouldn't live in the portal. The portal collects them and hands them to payroll, and then they're gone from the portal. Otherwise we've got two places to protect instead of one.

[00:01:45] Felix: That's doable. We pass them through to the payroll interface and don't store them on our side.

[00:01:50] Hannah: Good, let's make that a rule then. Bank and tax details go straight to payroll and aren't kept in the portal.

[00:01:57] Joel: The other big one is right to work. We have to see the original passport or the share code on day one. That's the law, we can't just take a photo.

[00:02:05] Ben: Can they upload it in advance, though? So at least we know before they turn up that it's the right document?

[00:02:10] Joel: Upload in advance, yes, so we can check it's the right type of document. But someone in HR still checks the original in person on day one and ticks it off.

[00:02:18] Hannah: Okay. So the starter uploads their right to work document before day one, and HR still checks the original in person on their first day and records that it's done.

[00:02:27] Amira: And those images get deleted after the check. I'll put that in my review, but just flagging it now.

[00:02:32] Joel: Hmm, we've always kept a copy for audit. The Home Office can ask to see it.

[00:02:36] Amira: Then we need to talk about that properly, because a portal full of passport scans is exactly what gets stolen.

[00:02:41] Hannah: Let's note that one and come back to it. I don't want to decide it in five minutes.

[00:02:45] Joel: Policies next. Code of conduct, IT security and data protection. At the minute they sign a printed page saying they've read them, which, let's be honest, nobody has.

[00:02:54] Felix: We can show each policy in the portal and have them confirm they've read it, with the date and time recorded.

[00:03:00] Hannah: Yes. The three policies, read and acknowledged in the portal, with the date and time kept.

[00:03:06] Felix: I had an idea here, actually. What if we turned the policies into a little welcome quiz? Badges, a progress bar, "you're eighty percent ready for day one". Makes it a bit more fun.

[00:03:15] Joel: For the data protection policy? I'm not sure badges are the vibe.

[00:03:19] Hannah: I like the progress bar. Badges I'm less sure about. Let's not commit to the quiz for September. Keep it as an idea.

[00:03:25] Felix: Fair enough.

[00:03:27] Ben: Can I do the manager bit? Because this is the bit I actually care about. When someone joins my team I've got a list in my head. Desk, buddy, first week plan, invite them to the team meeting, get them on the claims training. And every time I forget one. I'd love the portal to give me a checklist.

[00:03:43] Hannah: A checklist for the hiring manager, with the things they need to do before and during the first week.

[00:03:48] Ben: And remind me. If it's three days before they start and I haven't done the desk, nag me.

[00:03:53] Felix: Reminders by email are easy.

[00:03:56] Hannah: Okay, checklist and email reminders for the manager.

[00:04:00] Ben: Oh, and while I'm here, between us, my team lead in claims is leaving at the end of next month, she's handed her notice in but it's not announced yet. So I'll be the one onboarding everyone for a bit. Don't say anything.

[00:04:11] Hannah: Thanks Ben. Let's keep that out of the notes.

[00:04:14] Amira: IT side. The laptop and the accounts. The reason starters don't have a laptop is we hear about them too late. We need ten working days to get a laptop built and shipped.

[00:04:24] Hannah: So if the IT request was raised automatically the moment the offer's accepted, that would solve most of it?

[00:04:30] Amira: Most of it, yes. The account and the laptop request get created automatically when the offer's accepted, with the start date and the team. Then it's on us.

[00:04:39] Ben: What about when someone starts in a week, though? We had a guy last month who could start on the Monday, so we said yes.

[00:04:45] Amira: Then they won't have a laptop. I can't build one in three days without stealing it from someone else.

[00:04:50] Hannah: So what do we do for those? Loan laptops? Push the start date?

[00:04:54] Amira: I don't know, honestly. That's a policy call, not an IT one.

[00:04:58] Hannah: Okay, that's open. What happens when someone's start date is less than ten working days after they accept.

[00:05:04] Joel: Last thing from me. Diversity monitoring. We're supposed to be collecting the equal opportunities questions, ethnicity, disability and so on, and at the minute it's a paper form that most people don't return.

[00:05:15] Amira: That's special category data. If we're collecting it, it needs a lot of care.

[00:05:20] Hannah: I need to check with legal what we're allowed to do there before we put it anywhere. Park it for now.

[00:05:25] Joel: Sure. Oh, and on that, I'll be honest, we've had a real issue. Leon, who started in claims last month, told us he has epilepsy and asked for an adjustment to his screen setup, and we lost the form. He had to tell three different people. That's partly why I care about this.

[00:05:39] Hannah: Joel, that's really important, but please let's not use names. The point is that starters should be able to ask for adjustments in one place. Let's come back to how that works in the design review.

[00:05:49] Joel: Yes, sorry. Good point.

[00:05:51] Felix: Can I check scope? Contracts. Are we doing contract signing in the portal?

[00:05:56] Hannah: No. Contracts stay in the e-signature tool, it works and legal like it. The portal just links to it.

[00:06:02] Ben: And probation reviews? Could the portal track those too? Three month review, six month review.

[00:06:07] Hannah: Not in the first release. Probation stays in the HR system as it is. Let's get the first month right before we take on more.

[00:06:14] Felix: And contractors and temps? Do they get the portal?

[00:06:18] Hannah: Good question. The brief says permanent employees. Temps come through the agency. Contractors, I'm not sure. Let me think about that one.

[00:06:25] Joel: Before we finish, does anyone know if the office move is still happening in October? Because I've got a starter asking which building to go to.

[00:06:31] Hannah: Still October as far as I know, but don't quote me. Right, let me sum up. Personal details, emergency contact, bank and tax details in the portal before day one, bank and tax straight to payroll and not stored. Right to work uploaded in advance, original checked in person on day one, and what we keep is open. Three policies acknowledged with a timestamp. Manager checklist with reminders. IT account and laptop request raised automatically on acceptance, short-notice starters open. Diversity monitoring parked until legal comes back. Contracts stay in e-signature. Probation stays in the HR system. Contractors open. The quiz is an idea, not a commitment.

[00:07:12] Felix: Got all of that. I'll turn it into a design for the review in two weeks.

[00:07:17] Hannah: Thanks everyone.
