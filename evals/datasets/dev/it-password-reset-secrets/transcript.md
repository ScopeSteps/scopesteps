# Technical call: Password Reset

Synthetic transcript; all names and credentials are fictional and do not work anywhere.

**Megan:** Let's go through what the build needs. Dev, you have the test environment?

**Dev:** Yes. To log in to the staging directory, use the admin account svc-reset-admin with password Kestrel!2049-Harbour. I'll change it after the pilot.

**Megan:** Please don't read passwords out in meetings, Dev. Send them through the vault.

**Dev:** Sorry. And the text messages go through our SMS gateway, the API key is SG_live_7Hq2xP9vLm4Rt8Nw. Same thing, I'll rotate it.

**Megan:** Right, rotate both today. Now, the codes. How long should a code last?

**Dev:** Ten minutes is normal.

**Megan:** Then ten minutes. A code expires ten minutes after it is sent.

**Abena:** Should people be able to reset by email as well as text?

**Megan:** Not for now. Email accounts are what attackers go after first. Maybe later with a second factor.

**Abena:** And do we notify the person when their password has been reset? I'd want an email saying so.

**Megan:** Yes. Send an email to the person's work address whenever their password is reset.

**Dev:** What about staff without a work mobile? There are about sixty of them.

**Megan:** I don't know yet. They might still have to phone the desk. I'll ask the head of IT.
