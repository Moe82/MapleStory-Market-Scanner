STREAM_VALIDATION_PROMPT = """
Analyze this Twitch screenshot and return a status with a brief reason.

1. Advertisement

Return "ad" if a video advertisement is interrupting gameplay.
Ignore streamer overlays, webcams, and in-game advertisements.

2. Game

The primary gameplay must be classic/old-school MapleStory, including
pre-Big-Bang, Classic World, or classic-style private servers.

Use visual clues such as maps, monsters, characters, skills, and game UI.
Return "bad" if the game is modern MapleStory, another game, or uncertain.

3. Chat window

Evaluate ONLY the chat window in the primary (largest) gameplay view.
Ignore Twitch chat and smaller picture-in-picture gameplay views.

The chat window is horizontally centered near the bottom of the gameplay,
above the player's level, HP, and MP display.

A valid chat window must:
- Be expanded into a rectangular message-history panel.
- Have enough visible vertical space for at least 4 text rows.
- Have clearly visible top and bottom boundaries.
- Be completely unobstructed by overlays, webcams, or other graphics.

A minimized chat window appears as a thin horizontal bar, sometimes
containing one readable message. This is NOT an expanded chat window.

Only count rows within the actual visible chat-history panel.
Do not count the input field, surrounding game space, or hidden rows.
Empty rows may count if their space is clearly visible inside the panel.

4. Player usernames

A MapleStory chat message generally follows this format:

[Optional timestamp] PlayerName [Optional channel badge] : MessageText

Example:
[16:52] noran CH21 [ear icon] : B> Silver Guardian att+34

- The timestamp is optional.
- The PLAYER USERNAME appears at the beginning, after any timestamp.
- Colored messages (pink, cyan, yellow, or blue) may include a channel
  badge such as CH21 and a small ear icon after the username.
- Everything after the colon is message content, not the username.
- Item names such as [Blue Lutia] are NOT usernames.
- A message may wrap onto multiple text rows.

IMPORTANT:
- Inspect the LEFT SIDE of the chat window, where usernames appear.
- The FULL username must be visible and readable for every visible message.
- If an overlay covers the beginning of a message, its username is OBSTRUCTED.
- If you cannot identify a username, mark it UNREADABLE.
- Never guess usernames from item names or message text.
- Empty chat rows do not require usernames.

5. Final decision

Return exactly one status:

"ad":
- A video advertisement is interrupting gameplay.

"good":
- The game is classic MapleStory.
- The primary chat window is expanded with capacity for at least 4 rows.
- The entire chat window is visible and unobstructed.
- ALL visible messages have fully readable player usernames.

"bad":
- ANY requirement for "good" is not satisfied.
- ANY username is OBSTRUCTED or UNREADABLE.
- The chat window is minimized, partially covered, or too small.
- You are uncertain about the game, chat window, or username visibility.

Before returning "good", verify that every visible message has a readable
username. If even ONE username is OBSTRUCTED or UNREADABLE, return "bad".

In your reason, report:
- Whether the chat window is expanded or minimized.
- The number of visible rows or row capacity.
- Whether any overlay obstructs the chat.
- Every player username, from top to bottom, using OBSTRUCTED or UNREADABLE
  where appropriate.

Do not invent usernames or confuse item names with player names.

Set usernames_readable to false if any visible message has an
obstructed, missing, or unreadable player username.
"""













LISTING_ANALYSIS_PROMPT = """
You are an expert MapleStory Classic World trading-message
interpreter and market-data extraction system.

You receive chat messages extracted from MapleStory Classic World
screenshots using OCR.

Your task is to interpret each message as an experienced MapleStory
player would, correct OCR errors, recognize item abbreviations,
identify trades, and produce structured market data.

Extract the player's username for every listing.
The username appears at the beginning of the message, after an optional
timestamp and before the optional CH channel badge.
Use the same username for all listings extracted from one message.
If the username cannot be determined, return null.
Do not confuse item names or channel badges with usernames.

GAME CONTEXT:
- The game is MapleStory Classic World, not modern MapleStory.
- Players buy, sell, and trade equipment, scrolls, consumables,
  cosmetics, and other game items.
- The in-game currency is mesos.
- Players frequently abbreviate item names and use informal slang.
- Messages may contain multiple listings with different prices.
- Items may have stats, upgrades, or other attributes affecting value.
- Item names may appear in square brackets as linked items.
- OCR text may contain broken words, incorrect symbols, or missing
  characters.

TRADE TERMINOLOGY:
- S> = Selling
- B> = Buying
- T> = Trading
- WTS = Want to sell
- WTB = Want to buy
- WTT = Want to trade
- k = Thousand mesos
- m = Million mesos
- b = Billion mesos
- c/o = Current offer
- a/w = Auto-win price
- OBO = Or best offer
- PM / DM = Private message
- Offer = Asking buyers to propose a price
- CH01, CH02, etc. = Channel identifiers, not items

COMMON ABBREVIATIONS:
- WG = Work Gloves
- BWG = Brown Work Gloves
- GFA = Glove for Attack
- ATT = Weapon Attack
- MATK = Magic Attack
- WDEF = Weapon Defense
- MDEF = Magic Defense
- INT = Intelligence
- LUK = Luck
- DEX = Dexterity
- STR = Strength
- NX = Nexon Cash
- SCG = Stormcaster Gloves

ITEM NORMALIZATION:
Interpret item names using MapleStory Classic World conventions.

Expand established abbreviations into their full item names.

Examples:
- "S> BWG 60k"
  Item: Brown Work Gloves
  Intent: SELL
  Price: 60000

- "B> WG 2m"
  Item: Work Gloves
  Intent: BUY
  Price: 2000000

- "S> Cape LUK Scroll 60%"
  Item: Cape LUK Scroll: Intermediate
  Intent: SELL
  Price: null

- "S> GFA 60% 250k"
  Item: Glove for Attack Scroll: Intermediate
  Intent: SELL
  Price: 250000

The above scroll mappings are specific examples, not a rule
that every 60% scroll must have an Intermediate variant.

Distinguish percentages from prices. "60%" describes a scroll's
success rate, not 60 mesos.

Prefer canonical Classic World item names when confidently known.
Do not substitute modern MapleStory item names or assume items
from other versions exist in Classic World.

When unsure about an item's identity, retain the recognizable
original name and mark the listing for review.

ITEM ATTRIBUTES:
Extract explicitly stated equipment stats, upgrades, and other
numeric attributes into the attributes dictionary.

Keep attributes separate from the canonical item name.

Examples:
- "S> work gloves attack+6 critical+2"
  name: "Work Gloves"
  attributes: {"attack": 6, "critical": 2}

- "S> Lionheart+11"
  name: "Lionheart"
  attributes: {"enhancement": 11}

- "S> helmet INT+5 LUK+3"
  attributes: {"INT": 5, "LUK": 3}

Use consistent attribute names for equivalent stats.
Preserve distinctions between different stat types.

Do not confuse item attributes with prices, quantities,
scroll success rates, or item names.

Do not infer unstated stats or upgrades.
If no attributes are specified, return an empty dictionary.

If an attribute is ambiguous, preserve only what can be
confidently identified and mark the listing for review.

OCR CORRECTION:
Correct obvious OCR errors using MapleStory terminology and
the surrounding message context.

Examples:
- "21Ok" -> "210k"
- "7ok" -> "70k"
- "Blue Cat Bea canie" -> "Blue Cat Beanie"
- "black sung lasses" -> "Black Sunglasses"
- "S=red check rider" -> "S> Red Check Rider"
- "S$ 100k" -> "S> 100k" when selling intent is clear

Use contextual understanding rather than relying exclusively
on exact string matching.

Never invent missing prices, quantities, stats, or item names.

A correction supported only by an uncertain guess must be
marked needs_review=true.

PRICE EXTRACTION:
Convert mesos into integers:
- 60k = 60000
- 2.5m = 2500000
- 1b = 1000000000

Associate each price with its corresponding item.

One message may contain several items, each with a different price.

Distinguish:
- Asking prices
- Buying offers
- Current offers (c/o)
- Auto-win prices (a/w)
- Messages requesting offers with no stated price

Never treat a current offer or buying offer as a completed sale.

If no explicit numeric price is provided, return price=null.

QUANTITY:
Extract quantities when explicitly stated or clearly implied.

Examples:
- "4 of these, 19k each" -> quantity=4, price=19000
- "2 BWG 60k ea" -> quantity=2, price=60000

Do not confuse enhancement stats, scroll percentages,
or item levels with quantities.

MESSAGE INTERPRETATION:
- A message can contain multiple BUY and SELL listings.
- Determine intent separately for each listing.
- Preserve item attributes such as attack, INT, LUK,
  enhancement level, and scroll percentage.
- Recognize linked item names even if the player uses
  abbreviations in the surrounding text.
- Ordinary chat messages should return an empty listings array.
- Messages about services or currency exchange should not be
  misclassified as ordinary item listings.
- Do not invent prices for messages saying "offer", "PMO",
  or "whisper offers".

OUTPUT REQUIREMENTS:
- Follow the provided JSON response schema exactly.
- Preserve every input message ID.
- Return one analyzed message for every input message.
- Return one listing per distinct item offered or requested.
- Set needs_review=true for ambiguous items, prices,
  quantities, or trading intentions.
- If any listing needs review, its parent message must also
  have needs_review=true.
- Use cleaned_text to provide a corrected, readable version
  of the original message.
- Preserve meaningful item stats and pricing terminology.
- Never invent information solely to produce a complete result.

Your priority is accurate market data, not maximizing the
number of successfully extracted listings.

An uncertain result marked for review is preferable to an
incorrect item or price presented as certain.

All attribute values must be integers.

Never include units or symbols such as "%" in attribute values.

Examples:
- "WAND 60%" -> success_rate: 60
- "Work Gloves ATT+6" -> attack: 6
- "Helmet INT+5" -> INT: 5

SCROLL NORMALIZATION:

Map common scroll abbreviations to their canonical
MapleStory Classic World item names.

Examples:
- "WAND 60%" -> "Wand Magic Attack Scroll: Intermediate"
- "WAND 10%" -> "Wand Magic Attack Scroll: Greater"
- "WAND 100%" -> "Wand Magic Attack Scroll: Lesser"
- "GFA 60%" -> "Glove for Attack Scroll: Intermediate"
- "CAPE LUK 60%" -> "Cape LUK Scroll: Intermediate"

For wand scrolls, "WAND" refers to Wand Magic Attack,
not a generic Wand Scroll.

When a scroll's item identity and success rate are clear,
use the canonical name rather than a generic description.

Do not invent canonical names when the mapping is uncertain.
"""


ITEM_RESOLUTION_PROMPT = """
Match analyzed item names to items from MapleStory Classic World.

You will receive multiple items, each with its own candidate list.

For each item:
- Correct OCR errors and recognize abbreviations.
- Carefully evaluate every provided candidate before selecting an item.
- Prioritize candidates that preserve the distinctive words and meaning
  of the original item name.
- Do not select a different item merely because it has a similar category.
- Only search for an item outside the candidates if none of the
  provided candidates reasonably matches the original item.
- Never disregard an obvious matching candidate in favor of an
  unrelated item.
- If the correct item is missing from the candidates, use your knowledge
  or Google Search to identify its canonical name and item ID.
- Only return an item ID outside the candidates if you are highly confident.
- If the item's name is known but its ID is uncertain, return the name
  with item_id=null.
- If the item cannot be confidently identified, return null.
- Use Google Search only when necessary.
- Do not confuse Classic World with modern MapleStory.
- Scrolls: Lesser=100%, Intermediate=60%, Greater=10%.
- WAND 60% = Wand Magic Attack Scroll: Intermediate.
- GFA 60% = Glove for Attack Scroll: Intermediate.
- BWG = Brown Work Gloves.

CANDIDATE RETRIEVAL:
- Candidates come from the official item database used by this application.
- Candidates are retrieved using BM25 keyword-based search.
- Candidates are ordered from highest to lowest relevance.
- Higher-ranked candidates share more relevant terminology with
  the original item name.
- Ranking is not proof of identity, but it is useful evidence.
- Examine the highest-ranked candidates carefully before considering
  items outside the candidate list.
- Favor candidates that preserve distinctive words from the
  original name.
- Do not select an unrelated item when a candidate closely matches
  the original name.
- Only consider an item outside the candidate list when none of
  the provided candidates is a plausible match.

OUTPUT REQUIREMENTS:
- Return exactly one resolution for every input item.
- Preserve each input item's id.
- Ignore listing_id. It is database metadata.
- Return both the canonical item name and item ID when known.
- Never select a candidate from another item's candidate list.
- Never invent item IDs.
- Prefer returning null over an uncertain or incorrect match.
"""