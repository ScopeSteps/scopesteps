import { useState } from 'react';

import { Button } from '@/components/Button';
import { TextField } from '@/components/TextField';
import { copyText } from '@/lib/clipboard';

/** An invitation link to share privately, with a copy button and the field to copy it by hand. */
export function CopyLink({ link }: { link: string }) {
  const [copied, setCopied] = useState<boolean | null>(null);
  return (
    <div className="flex flex-col gap-2">
      <TextField label="Invitation link" value={link} readOnly />
      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          onClick={() => {
            void copyText(link).then(setCopied);
          }}
        >
          Copy link
        </Button>
        <span role="status" className="text-[13px] text-subtle">
          {copied === true && 'Copied. Works once, expires in 7 days.'}
          {copied === false && 'Your browser blocked copying: select the link and copy it.'}
        </span>
      </div>
    </div>
  );
}
