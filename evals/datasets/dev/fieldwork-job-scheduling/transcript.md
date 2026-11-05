# Requirements workshop, Fieldwork job scheduling

Synthetic transcript; all names are fictional. Recorded and transcribed by Teams.

[00:00:04] Tom: Can everyone hear me? I've got the little spinning thing again.

[00:00:09] Kemi: Yeah, we can hear you. You're frozen on the screen though, you look like you've seen a ghost.

[00:00:15] Tom: That's just my face on a Monday. Did you get out on the river in the end, Rachel? You said you were going Saturday.

[00:00:22] Rachel: We did, for about an hour, and then it chucked it down and we sat in the car eating crisps. My son caught a weed. Very proud of it.

[00:00:31] Kemi: That's still more than I caught. My daughter had football at eight in the morning, in that wind, and they lost nine nil. Nine nil. I didn't know you could lose nine nil at under tens.

[00:00:41] Dev: You can lose anything at under tens.

[00:00:44] Rachel: Right, okay, let's make a start, Lucy's only got us till eleven. So, thanks for coming. The point of today is to agree what the first release of Fieldwork actually does for a technician and for the desk, so Lucy and her team at Brightline can firm up the build. I've got the brief up, you've all seen it. I'd like to come out of this with a list we all sign up to.

[00:01:08] Lucy: Yes, and from our side the main thing is to know what's in for March and what's later, because that drives the plan and the cost. So I'll be pushing you on that, sorry in advance.

[00:01:17] Rachel: That's fine, that's what we need. Kemi, do you want to start with the technician's day, because that's the heart of it.

[00:01:24] Kemi: Yeah. So basically at the minute, right, you get a phone call at quarter to eight from Tom or whoever's on the desk, and they read you your jobs, and you write them on the back of your hand or whatever. And then half the time the order's daft, you're driving past one job to get to another. So what the lads want, first thing, is to open the phone and see the day, in order, with the address and how to get in. The access notes are massive. "Key under the blue pot", "dog in the garden, ring first", that kind of thing.

[00:01:58] Tom: And the parts. If it's a meter swap they need to know which meter before they leave the depot, otherwise they're driving back for it.

[00:02:05] Kemi: Yeah, the parts for the job, so you can check the van before you go.

[00:02:09] Rachel: Okay. So the day's jobs on the phone, in the order they should do them, with the address, the access notes and the parts. I think that's the core of release one, is everyone agreed?

[00:02:18] Dev: Agreed. The order comes from the desk though, right? We're not doing route optimisation.

[00:02:23] Tom: The desk sets the order. We know the patches better than any algorithm, honestly.

[00:02:28] Lucy: Good, because route optimisation is a whole other product. So the order is whatever the dispatcher sets, and the technician sees it.

[00:02:35] Rachel: Yes. Desk sets the order.

[00:02:38] Kemi: Can I just say while we're on the North, we're two down this week anyway. Gary's off with his back again, the disc thing, and he's waiting on the scan, so that's why North looks so thin on the sheet. Not that that's a Fieldwork thing.

[00:02:50] Rachel: Thanks Kemi, let's maybe keep that one for the team meeting.

[00:02:54] Kemi: Yeah, sorry, sorry.

[00:02:57] Rachel: No, it's fine. Tom, the desk side.

[00:03:00] Tom: So for us the big one is moving work about during the day. Someone gets stuck on a burst that takes four hours instead of one, and I've got three jobs sat behind him. At the minute I'm ringing round. What I want is to see every job and where it's up to, started, finished, stuck, whatever, and just drag a job from one technician to another, and it turns up on their phone.

[00:03:21] Lucy: And the technician gets told it's changed? A notification?

[00:03:24] Tom: Yeah, it has to buzz, they're not staring at the phone when they're up to their knees in a hole.

[00:03:28] Rachel: So dispatchers can see the status of every job and reassign a job to another technician during the day, and the technician gets a notification when their list changes. Yes.

[00:03:37] Dev: Who's allowed to reassign, just the supervisors or anyone on the desk?

[00:03:41] Tom: Anyone on the desk. There's five of us and I'm not always in.

[00:03:45] Rachel: Let's say any dispatcher. Fine.

[00:03:48] Kemi: Now this is the bit I really care about. Signal. Half the North is no signal. The new estates are fine but the old village streets, the cellars where the meters are, the pumping stations, nothing. If the app needs signal to show you your jobs, it's dead in the water. Pun intended.

[00:04:04] Lucy: So, on that, in the statement of work offline mode is in phase two, not March. It's a big chunk of work, because you're syncing changes both ways and handling conflicts.

[00:04:13] Kemi: Then March is no good to us, to be honest.

[00:04:16] Dev: Could we split it? Seeing your day without signal is much easier than editing without signal. You download the day in the morning at the depot, and it's there.

[00:04:24] Lucy: Read-only offline is a lot less work, yes. Editing offline, completing jobs offline, that's the hard part.

[00:04:30] Kemi: Seeing it is the main thing. If I can see the job and the access notes in a cellar, I can fill the rest in when I'm back up the steps.

[00:04:37] Rachel: Okay. Then I'm going to make a call on this. The technician can see their day's jobs without signal in the first release. Completing a job without signal waits for phase two. Lucy, I know that's not in the statement of work as it stands, so you'll need to price it.

[00:04:50] Lucy: I'll price it this week. I'll warn you now it won't be free.

[00:04:53] Rachel: Understood.

[00:04:55] Tom: Can I go and put the kettle on? I'm going to miss the next bit otherwise, I've been on since six.

[00:05:00] Rachel: Go on, two minutes. Kemi, carry on with the job record while Tom's out.

[00:05:05] Kemi: So when you finish a job, right, at the minute you fill the paper sheet: what you did, what parts you used, start and finish time, and the customer signs if they're in. Then it sits in the van till Friday. So we want to do that on the phone, and take photos. Photos are big, because if there's a complaint later, "you left my drive in a state", we've got proof.

[00:05:26] Lucy: Photos attached to the job record. How many per job?

[00:05:29] Kemi: Depends, two or three usually. Sometimes more on a big dig.

[00:05:33] Dev: We'll want a limit, for storage. I'll check with Tom what's sensible.

[00:05:37] Rachel: Fine. So the technician completes the job record on the phone, what was done, the parts used and the times, with photos attached.

[00:05:44] Kemi: And the signature. Honestly half the time there's nobody in. You can't make the customer signing compulsory or you can never close a job.

[00:05:51] Rachel: Signature when the customer's there, then, and the job can be closed without one.

[00:05:55] Lucy: Optional signature. Got it.

[00:05:58] Tom: I'm back. What did I miss? Did we agree we're all getting a pay rise?

[00:06:02] Kemi: Ha, I wish. We're not paid enough to be chasing customers for signatures, I'll tell you that for nothing.

[00:06:07] Rachel: Let's not go there today. Customers next. The brief says a two-hour window instead of eight till six. Tom, how would that actually work?

[00:06:15] Tom: So if the order's set the night before, we can work out roughly when each job lands. Two hours either side of that is honest. At the minute we tell them all day because we don't know.

[00:06:24] Lucy: We could send the customer a text the evening before with their two-hour window. That's standard in the product, we've got an SMS module.

[00:06:31] Rachel: That's what I had in my head, yes. The customer gets a two-hour arrival window, and a text the evening before telling them.

[00:06:38] Dev: Do we need them to be able to reply to it? Like rebook?

[00:06:42] Lucy: Rebooking by text is a different feature. That's not in the module out of the box.

[00:06:46] Dev: I was going to say, we could put a little chatbot on the website, so customers can rebook themselves. Takes a load off the desk.

[00:06:53] Tom: A chatbot. For our customers. Half of them still ring to ask if the water's safe after a tap's been off.

[00:06:59] Rachel: Let's park the chatbot. Not for March. It's an idea for later, maybe.

[00:07:03] Dev: Fair. I'll write it down somewhere.

[00:07:06] Rachel: Emergencies. Tom, this is where it gets interesting.

[00:07:09] Tom: So when a burst comes in, I need to send the nearest free person. At the minute I'm guessing from the sheet where everyone is. If the app could show me where everyone is on a map, I'd send the right person every time.

[00:07:21] Kemi: Yeah, so this is the bit the lads are worried about. Nobody wants to be tracked all day. Where you stop for your dinner, how long you're in the cafe. There's a lot of people saying if the phone's tracking them they'll leave it in the van.

[00:07:33] Tom: I don't care where they have their dinner, I care where the burst is.

[00:07:36] Kemi: I know you don't, but it's not you, is it, it's whoever has the data after you.

[00:07:41] Rachel: This is a real concern and I don't want to decide it in this room. The union reps need to be part of it. What I will say is the desk can flag a job as an emergency and it goes to the top of a technician's list. Whether we show technicians' locations on a map, and when, is open until we've talked to the union.

[00:07:58] Lucy: So for the build, emergency flag yes, live location undecided.

[00:08:02] Rachel: Correct.

[00:08:04] Dev: Can I raise one on the systems side? Billing. The whole point is to stop waiting for the paper. So when a job's completed, the record needs to go to the billing system. I'd say end of each day is fine, it doesn't need to be instant.

[00:08:17] Rachel: End of day is fine for billing.

[00:08:19] Dev: And the asset register as well, when a meter's swapped, the new meter serial has to go on the register.

[00:08:25] Lucy: We'll need the register's interface spec for that. I've not seen one.

[00:08:29] Dev: There isn't really one yet. That's my problem, not yours. Leave it with me.

[00:08:33] Kemi: What about timesheets? If we're doing everything on the phone, can we do our hours and overtime on it as well? We still do overtime on a paper form.

[00:08:41] Rachel: No. Timesheets and overtime stay in the HR system. I don't want Fieldwork anywhere near pay. That's a firm no for this project.

[00:08:48] Kemi: Worth a try.

[00:08:50] Lucy: One more for me. How long do we keep the job records and photos? Is it forever, seven years, something else? It affects the storage cost.

[00:08:58] Rachel: I genuinely don't know. That's a question for our records manager. Can I come back to you?

[00:09:03] Lucy: Of course. I'll put it down as open.

[00:09:06] Tom: Before we wrap up, are we still doing the depot car park thing next week? Because I'm not parking on the road again, I got a ticket last time.

[00:09:13] Rachel: That's facilities, Tom, I'll chase them. Right. Let me read back what I've got. Day's jobs on the phone in the desk's order, with address, access notes and parts. Dispatchers see every job's status and any dispatcher can reassign, technician gets a notification. Day's jobs visible without signal in March, completing without signal is phase two. Job record on the phone with photos, signature optional. Two-hour window with a text the night before. Emergency flag puts a job top of the list. Completed jobs to billing at the end of each day. Asset register, Dev's looking into. No timesheets or overtime. Chatbot parked. Location tracking open until the union meeting. Retention open. Have I missed anything?

[00:10:01] Kemi: That's it. That's actually loads.

[00:10:04] Lucy: That's very clear, thank you. I'll send the pricing for offline viewing by Friday.

[00:10:09] Rachel: Thanks everyone. Same time in two weeks.
