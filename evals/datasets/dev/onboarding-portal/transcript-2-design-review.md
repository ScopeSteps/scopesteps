# Design review, Welcome new starter portal

Synthetic transcript; all names are fictional. Recorded and transcribed by Teams.

[00:00:03] Hannah: Morning. Felix, you've got the screens?

[00:00:08] Joel: Before we start, has everyone seen the comments on Felix's early design? I left about twenty. Sorry, Felix.

[00:00:18] Felix: Twenty-three. I counted. They were good comments, though. Most of them are in.

[00:00:26] Amira: I left four, all about passwords. Which is why I'm happy with what I've heard about sign-in.

[00:00:36] Felix: I have. Give me one second, I'm sharing the wrong window. That's my kitchen quote. Please don't look at the price of tiles.

[00:00:48] Sophie: Too late. Is that per tile?

[00:00:53] Felix: Per square metre, thankfully. Right, here we go. So I've taken everything from the workshop and turned it into the starter's journey. Before we go through it, Hannah, did legal come back on the open bits?

[00:01:10] Ben: Is that the kitchen you were talking about at the summer party? The one that was going to take six weeks?

[00:01:21] Felix: It's now week eleven. The builder has discovered a joist. Apparently that's bad.

[00:01:29] Sophie: Joists are always bad. My brother's extension found a joist and it added two months.

[00:01:38] Hannah: Can we discover screens instead of joists, please? Go on, Felix.

[00:01:45] Felix: So the journey goes like this. The offer's accepted, the contract's signed in the e-signature tool, and then the starter gets one email from the portal with a link. Everything happens from that link. I've tried to keep it to five steps, so it doesn't feel like a mountain.

[00:02:08] Joel: One email. Not nine.

[00:02:12] Felix: One email.

[00:02:16] Joel: I might cry.

[00:02:20] Hannah: Some of them. I'll go through as we hit them.

[00:02:27] Felix: Great. So, first screen, signing in. Starters don't have a company account before day one, so they sign in with their personal email address and a one-time code we send them each time. No password to remember.

[00:02:45] Ben: Does the code come by text or email?

[00:02:51] Felix: Email, to the personal address they gave us. Text would need their phone number to be right, and you know how often that's wrong.

[00:03:03] Sophie: Very often.

[00:03:07] Ben: What if they don't get the email? It goes to spam?

[00:03:14] Felix: There's a "send it again" link, and the email comes from our real domain, so it should land properly. The service desk can also check whether it was sent.

[00:03:28] Amira: And the code expires after ten minutes, so if someone does get hold of an old email, it's useless.

[00:03:38] Amira: That's what I wanted. The one-time code is our second factor, effectively. And if the offer's withdrawn, the access has to stop the same day.

[00:03:51] Joel: How does the portal know an offer's withdrawn?

[00:03:57] Felix: When HR marks it in the HR system, it tells the portal. That's an existing feed.

[00:04:06] Joel: So it's on us to mark it promptly.

[00:04:12] Hannah: Yes, and that's a process thing for your team, not a portal thing. Same day.

[00:04:21] Joel: Same day. I'll put it in our checklist.

[00:04:27] Hannah: Agreed. Starters sign in with their personal email and a one-time code, and access ends the day an offer is withdrawn.

[00:04:38] Felix: Then the home screen. This is where the quiz idea ended up. No badges, I listened, but there's a progress bar showing how much they've done before day one.

[00:04:52] Sophie: What counts as done? If they've started the bank form but not finished it?

[00:05:00] Felix: Only finished steps count. A half-done form doesn't move the bar.

[00:05:07] Sophie: Good. Otherwise everyone's on ninety percent with nothing submitted.

[00:05:13] Ben: I love that. Can managers see it too?

[00:05:19] Felix: The manager sees the progress on their checklist page, yes. Not the details, just how far along.

[00:05:29] Hannah: Good. Progress bar for the starter, and the manager sees the overall progress but not the details.

[00:05:39] Felix: Then the forms, personal details, emergency contact, bank and tax. Bank and tax go straight to payroll on submit and nothing's kept on our side, as agreed.

[00:05:53] Sophie: And payroll gets told if they change them after submitting?

[00:06:00] Felix: Any change goes straight to payroll the same way.

[00:06:06] Sophie: And they get an email when they change them? So if someone else changed them, they'd know?

[00:06:16] Amira: That's a good control, actually. Fraud people love changing bank details.

[00:06:23] Felix: Yes, a confirmation email to the personal address whenever bank details change. That's easy.

[00:06:31] Hannah: Do that.

[00:06:35] Sophie: Perfect.

[00:06:39] Felix: Right to work. They upload the document, HR sees it in a queue, and on day one HR records that they've seen the original. Now, the bit that was open, how long we keep the images.

[00:06:56] Ben: Why does it take legal so long? Genuine question.

[00:07:02] Hannah: Because the guidance is genuinely unclear about digital copies held by a third-party system, and they don't want to give us an answer that's wrong. I'd rather wait a week than get fined.

[00:07:18] Joel: The fine's up to forty-five thousand pounds per person, by the way. Per person.

[00:07:26] Ben: Okay, I'll stop asking.

[00:07:30] Hannah: Legal haven't answered that one yet. Amira's review says delete thirty days after the check, Joel's team's list says keep a copy for audit. They're looking at the Home Office guidance. So that stays open, I'm afraid. Felix, build it so either is possible.

[00:07:51] Amira: As long as nobody quietly picks "keep forever" in the meantime.

[00:07:58] Felix: The default in the build will be the shorter option, deleting after thirty days, because it's easier to keep something longer later than to un-keep it.

[00:08:11] Amira: Thank you. That's the right default.

[00:08:16] Joel: As long as it's a default and not a decision.

[00:08:23] Hannah: It's a build default. The decision is still with legal and then me.

[00:08:31] Hannah: Nobody's picking anything until legal answers.

[00:08:36] Felix: Adjustments. This came out of what Joel said last time. There's an optional form where a starter can ask for reasonable adjustments, a different chair, screen settings, working hours, whatever they need.

[00:08:52] Joel: Can I say why this matters so much? At the moment, if someone needs an adjustment, they tell the recruiter, who tells me, who tells the manager, who tells facilities. Four handovers. Things get lost at every one.

[00:09:10] Ben: And the person has to explain themselves four times. Which is horrible.

[00:09:17] Felix: With the form, they explain once, and it goes to the right people.

[00:09:25] Joel: Who sees it?

[00:09:29] Felix: That's the question I wanted answered.

[00:09:34] Hannah: HR sees it. The manager only sees it if the starter agrees to share it. The starter ticks a box to say whether their manager can see it. Nobody else.

[00:09:49] Joel: That's much better than what happens now.

[00:09:54] Ben: And as the manager, if they say yes, I see what they need, but not why? Like, I see "standing desk", not the medical reason?

[00:10:07] Hannah: You see what they asked for. If they choose to tell you more, that's up to them.

[00:10:17] Ben: That feels right.

[00:10:21] Amira: And the form doesn't ask for a diagnosis at all. Just what would help.

[00:10:29] Felix: That's how I've designed it. Free text, "what would help you", and the share box.

[00:10:38] Felix: Diversity monitoring. Hannah, legal?

[00:10:42] Hannah: Legal said yes, we can collect it, but it has to be optional, every question has to have a "prefer not to say", and it's kept separate from the employee record and only used for anonymous reporting. HR advisers don't see individual answers.

[00:11:02] Joel: Not even me?

[00:11:06] Hannah: Not even you. Only the anonymous numbers.

[00:11:11] Joel: Fine by me. I don't want to see them, honestly. It's better that way.

[00:11:19] Sophie: Where does the gender pay gap data come from, then? Because that needs gender against salary.

[00:11:28] Hannah: That comes from the HR system, like it does now. It's a separate thing. The monitoring questions are about the broader diversity report.

[00:11:40] Amira: Separate store, no link back to the person in the reports. I can live with that.

[00:11:49] Felix: Then the short-notice starters. That was open as well.

[00:11:55] Amira: I've sorted that with Hannah. We're keeping a pool of ten loan laptops. Anyone starting less than ten working days after they accept gets a loan laptop on day one, and their own one follows.

[00:12:12] Ben: Ten feels like a lot of laptops sitting in a cupboard.

[00:12:19] Amira: Not in a cupboard. In the service desk store, locked, and they're reissued. When the starter's own laptop arrives, the loan one comes back, gets wiped and goes back in the pool.

[00:12:35] Ben: And if it doesn't come back?

[00:12:40] Amira: Then I go and find you.

[00:12:45] Ben: Noted.

[00:12:49] Hannah: Yes. The portal flags short-notice starters to the service desk so they get a loan laptop.

[00:12:58] Felix: How does the portal know it's short notice?

[00:13:04] Amira: Start date minus offer accepted date. Less than ten working days, flag it.

[00:13:12] Felix: Working days, so I need the bank holidays. I'll use the HR system's calendar.

[00:13:20] Joel: Use the Scottish one for the Glasgow office, they've got different bank holidays.

[00:13:28] Felix: Good catch. I'd never have thought of that.

[00:13:34] Ben: Can I ask about contractors? I've got two starting in October.

[00:13:41] Hannah: I thought about it. Contractors aren't in the first release. Their onboarding is different, they come through procurement. We can look again next year.

[00:13:53] Joel: For what it's worth, procurement are relieved. They were worried we'd break their process.

[00:14:01] Hannah: Their process is fine. It's just not ours.

[00:14:07] Ben: Okay, I'll do it the old way.

[00:14:12] Sophie: Can I say, completely off topic, did anyone else hear the CEO got a thirty percent rise in April? Apparently it's in the annual report.

[00:14:25] Hannah: Sophie. Not in this meeting, please.

[00:14:30] Sophie: Sorry. Gossip's my cardio.

[00:14:34] Ben: It's in the annual report, though, isn't it? So it's not really gossip.

[00:14:42] Hannah: Ben.

[00:14:46] Ben: Sorry. Moving on.

[00:14:50] Felix: The welcome screen. This is from Joel's original list. Before day one, the starter sees where to go, what time, and who to ask for at reception.

[00:15:04] Joel: That's the question we get most. "Which door do I go in?"

[00:15:11] Sophie: Especially with the move. Half the starters in October won't know which building.

[00:15:19] Hannah: The welcome page reads the office from their offer, so it'll be right. If the move date changes, HR updates the office and the page changes.

[00:15:32] Felix: Yes, it's not hard coded, it reads the office record.

[00:15:39] Felix: And there's a badge photo upload, from the same list. They upload a photo and security prints the badge before they arrive.

[00:15:51] Ben: Can they redo the photo if it's awful? Mine's from twenty sixteen and I look like a hostage.

[00:16:01] Felix: They can replace it until the badge is printed.

[00:16:07] Ben: Only until it's printed?

[00:16:11] Felix: After that, security would have to reprint it, and security don't like reprinting.

[00:16:19] Amira: Security really don't like reprinting.

[00:16:23] Amira: The photo goes to the badge system and gets deleted from the portal once the badge is printed.

[00:16:33] Felix: Fine by me.

[00:16:37] Joel: What are the photo rules? Because security rejected half of last September's photos. Sunglasses, hats, a cat.

[00:16:47] Felix: I'll put the rules on the upload screen. Plain background, face visible, no sunglasses.

[00:16:55] Ben: No cat.

[00:16:59] Felix: No cat.

[00:17:03] Amira: Two more from my review, while we're here. The portal has to meet the accessibility standard, WCAG 2.2 at level AA. And sessions time out after fifteen minutes without activity, because people will do this on shared laptops at home.

[00:17:22] Felix: Both fine. The HR platform supports both.

[00:17:27] Amira: And I'd like an accessibility test with real users before go-live, not just an automated checker.

[00:17:36] Felix: The HR platform team did that for the employee pages last year. I'll ask if we can reuse their testers.

[00:17:47] Hannah: Please do.

[00:17:51] Hannah: What about if an offer's withdrawn? How long do we keep what they've already put in?

[00:18:00] Joel: We don't have a rule for that today. Paper just goes in the shred bin eventually.

[00:18:09] Sophie: Bank details too?

[00:18:13] Joel: Bank details on paper, yes, shred bin. In the portal they'd already be in payroll, though.

[00:18:22] Sophie: Then payroll would need to delete them too, if someone never started. I'd need to check what we do today.

[00:18:33] Hannah: That's part of the same question for legal. Let's keep it as one open point and not split it up.

[00:18:44] Hannah: Then that's another one for legal. Let's mark it open. How long we keep a starter's information when their offer is withdrawn.

[00:18:56] Felix: Noted.

[00:19:00] Ben: Has anyone got a spare parking permit, by the way? Mine ran out and the new ones don't come till next month.

[00:19:12] Joel: Speak to facilities. They had some last week.

[00:19:18] Sophie: Ask for the green ones, not the blue ones. The blue ones are only for the old building.

[00:19:28] Ben: Of course they are.

[00:19:32] Hannah: Right, let me sum up what's new today. One-time code sign-in, access ends when an offer's withdrawn. Progress bar, manager sees progress but not details. Changes to bank details go straight to payroll. Right to work image retention still open, waiting on legal. Adjustments form, HR sees it, manager only with consent. Diversity questions optional, separate, anonymous reporting only. Loan laptops for short-notice starters, flagged by the portal. No contractors in release one. Welcome screen with where and when. Badge photo goes to the badge system and is deleted after printing. WCAG 2.2 AA and a fifteen minute timeout. Retention for withdrawn offers open.

[00:20:18] Felix: Perfect. I'll get going on the build.

[00:20:23] Joel: When will we see something working?

[00:20:28] Felix: A test version in about four weeks, for this group to try. I'll invite you all as fake starters.

[00:20:38] Ben: Can I be a fake starter called Dave?

[00:20:44] Felix: You can be whoever you like.

[00:20:49] Hannah: Thanks everyone. Four weeks, then.
