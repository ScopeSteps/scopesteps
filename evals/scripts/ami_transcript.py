"""Turn an AMI Meeting Corpus meeting into a pack transcript: one paragraph per speaker turn.

The AMI corpus (https://groups.inf.ed.ac.uk/ami/corpus/) and its manual annotations are released
under CC BY 4.0. This reads a meeting's per-speaker word files (`words/<meeting>.<A-D>.words.xml`
from `ami_public_manual_1.6.2.zip`) and `corpusResources/meetings.xml`, and writes Teams-style
turns, `[hh:mm:ss] Name: words`. Changes made to the corpus text, as the licence asks us to say:
speakers are labelled with fictional first names for their scenario roles, the participants'
own first names, where they say them, are replaced with those fictional names, vocal sounds,
gaps and disfluency markers are dropped, and words are joined into turns. Every other word is
unchanged, fillers ("um", "uh") included.

    python -I evals/scripts/ami_transcript.py <annotations-dir> ES2002a \\
        PM=Fiona ME=Owen UI=Callum ID=Martin Laura->Fiona David->Martin > transcript.md

Run it with `python -I` on a freshly downloaded, unzipped copy: the XML is untrusted data.
"""

import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

# The stdlib parser is enough for this one-off conversion: expat does not fetch external
# entities and limits entity expansion, and the input is the AMI archive, checked by hand.
NITE = "{http://nite.sourceforge.net/}"
# A pause this long, in seconds, ends one utterance and starts the next.
UTTERANCE_GAP_SECONDS = 1.0


@dataclass(frozen=True)
class Utterance:
    speaker: str
    start: float
    text: str


def speaker_roles(annotations: Path, meeting: str) -> dict[str, str]:
    """The scenario role (PM, ME, UI, ID) of each speaker letter in a meeting."""
    tree = ET.parse(annotations / "corpusResources" / "meetings.xml")  # noqa: S314
    for element in tree.getroot().iter("meeting"):
        if element.get("observation") == meeting:
            return {
                str(speaker.get("nxt_agent")): str(speaker.get("role"))
                for speaker in element.iter("speaker")
            }
    raise SystemExit(f"{meeting} is not in meetings.xml")


def utterances(path: Path, speaker: str) -> list[Utterance]:
    found: list[Utterance] = []
    words: list[str] = []
    start = last_end = 0.0
    for element in ET.parse(path).getroot():  # noqa: S314
        if element.tag != "w" or not (element.text or "").strip():
            continue
        begin = float(element.get("starttime") or last_end)
        end = float(element.get("endtime") or begin)
        if words and element.get("punc") != "true" and begin - last_end > UTTERANCE_GAP_SECONDS:
            found.append(Utterance(speaker, start, " ".join(words)))
            words = []
        if not words:
            start = begin
        text = (element.text or "").strip()
        if element.get("punc") == "true" and words:
            words[-1] += text
        else:
            words.append(text)
        last_end = max(last_end, end)
    if words:
        found.append(Utterance(speaker, start, " ".join(words)))
    return found


def transcript(annotations: Path, meeting: str, names: dict[str, str]) -> str:
    roles = speaker_roles(annotations, meeting)
    spoken = sorted(
        (
            utterance
            for letter, role in roles.items()
            for utterance in utterances(
                annotations / "words" / f"{meeting}.{letter}.words.xml", names[role]
            )
        ),
        key=lambda utterance: utterance.start,
    )
    turns: list[tuple[str, float, list[str]]] = []
    for utterance in spoken:
        if turns and turns[-1][0] == utterance.speaker:
            turns[-1][2].append(utterance.text)
        else:
            turns.append((utterance.speaker, utterance.start, [utterance.text]))
    return "\n\n".join(
        f"[{_clock(start)}] {speaker}: {' '.join(parts)}" for speaker, start, parts in turns
    )


def _clock(seconds: float) -> str:
    whole = int(seconds)
    return f"{whole // 3600:02d}:{whole // 60 % 60:02d}:{whole % 60:02d}"


def rename(text: str, renames: dict[str, str]) -> str:
    """Replace each spoken first name, as a whole word, with its fictional one."""
    for real, fictional in renames.items():
        text = re.sub(rf"\b{re.escape(real)}\b", fictional, text)
    return text


def main() -> None:
    annotations, meeting, *pairs = sys.argv[1:]
    names = dict(pair.split("=", 1) for pair in pairs if "=" in pair)
    renames = dict(pair.split("->", 1) for pair in pairs if "->" in pair)
    text = rename(transcript(Path(annotations), meeting, names), renames)
    sys.stdout.write(text + "\n")


if __name__ == "__main__":
    main()
