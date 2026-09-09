# Jingles CH-16 — 80 scripts + tag de signature

Radio **CH 16** / *Channel Sixteen* — clin d'œil au canal VHF 16, fréquence internationale
de détresse et d'appel. Écrit le 2026-09-07, à produire sur Suno.

Format identique à `SCRIPTS.md` (les 13 jingles Kalbass), avec en plus le prompt de style
Suno de chaque clip.

---

## Règles de production

Les 80 jingles sont écrits pour recevoir **le même tag final**, collé en post-traitement.
Trois contraintes en découlent — les casser fait sonner le tag comme un collage :

1. **Aucun jingle ne prononce « Channel Sixteen » en dernière réplique.** Le nom peut
   apparaître en cours de route ; c'est le tag qui le pose. Le n° 31 le chante faux exprès
   au milieu — le tag qui suit le corrige, c'est le gag.
2. **Fin sur une résolution nette** (sting, kick, coupure sèche), jamais sur un fondu.
3. **10 à 20 secondes** avant tag, soit 12 à 22 s finis — les durées cibles de chaque
   fiche intègrent déjà le temps des pauses ci-dessous. Les familles I à M sont plus
   courtes que les premières : une voix solaire n'a pas besoin de s'étendre.

### Registre des voix — pas de grosses voix graves

Les directions de jeu penchent vers le clair : *bright*, *warm*, *cheerful*, *sunny*,
*delighted*, *smiling audibly*, *light and breezy*. À éviter : *booming*, *colossal*,
*deep*, *menacing*, *ominous*. Une radio house n'est pas une bande-annonce de film
d'horreur — et une voix qui sourit s'entend.

Les familles **I à M** (n° 51 à 80) sont écrites entièrement dans ce registre, avec des
styles Suno assortis : *balearic*, *summer groove*, *nu-disco*, *uplifting house* plutôt
que *sub bass* et *deep dub*.

Dans les 50 premiers, **cinq** tirent encore vers le grave et méritent d'être ré-écoutés en
priorité, voire re-dirigés : **06** (deadpan + sub bass), **12** (capitaine *booming*),
**21** (Kraken — *colossal*, *immense low groan*), **39** (*faintly menacing*), **40**
(*heavy dub*). Les autres jingles tendus (07, 09, 10, 13, 34, 43) sont de l'énergie
comique, pas de la voix caverneuse : ils peuvent rester.

### Les pauses `[0.5seconds]`

Sans marqueur explicite, Suno ne respire pas : il attaque la voix dès la fin du
`[Sound FX: ...]`, et il **ignore les points à l'intérieur d'une réplique** — « belay that.
The party is on this one » sort d'une seule traite. Les pauses sont donc posées à deux
endroits :

- **après chaque `[Sound FX: ...]`**, pour que la voix ne démarre pas dans l'ambiance et
  pour ménager le temps comique avant la chute ;
- **à chaque point interne d'une réplique**, en coupant la réplique en deux segments entre
  guillemets avec la pause sur sa propre ligne. Le marqueur n'est jamais mis à l'intérieur
  des guillemets, où Suno risquerait de le lire à voix haute.

Pas de coupure sur `!` ni sur `?` : l'exclamation porte l'énergie, une pause la casse. Pas
de coupure non plus sur les points de suspension `...`, qui sont déjà un temps joué par le
comédien.

Trois jingles (43, 45, 50) portent un `[1second]` là où le silence long *est* la blague.
Seul `[0.5seconds]` est confirmé fonctionnel à ce jour : si `[1second]` n'est pas
interprété, le remplacer par deux `[0.5seconds]` sur deux lignes.

Les pauses sont **volontairement généreuses** : supprimer une ligne `[0.5seconds]` qui
traîne coûte une touche, alors que repérer une pause manquante coûte une génération. Là où
la réplique doit couler d'un trait — panique, ordres rapides, babillage — elle a été laissée
en un seul segment (n° 09, 12, 19, 43, 50).

### Le tag — cinq pistes à tester sur Suno

Premier essai (2026-09-07) : 0:04, 0:10 et 0:13 pour une cible de 2 s, deux générations
remboursées. Suno produit une longueur musicale minimale et ajoute intro, lit et ambiance ;
`no music` n'est pas une contrainte pour lui.

**Deuxième essai — changement de stratégie.** Deux choses ont changé depuis :

1. **Les marqueurs de pause fonctionnent.** On sait maintenant que `[0.5seconds]` et
   `[1second]` sont interprétés. Le silence est donc *demandable* — c'est ce qui manquait.
2. **Il ne faut plus demander 2 secondes.** Les deux échecs remboursés portaient sur la
   durée la plus courte. On demande un clip **normal** dont l'essentiel est du silence, et
   on découpe après. On joue avec la contrainte de Suno au lieu de la combattre.

**Direction de voix : chaleureuse, pas caverneuse.** Ce tag passe sur les 80 jingles — si
une seule voix ne doit pas faire peur, c'est celle-là. *Warm*, *bright*, *friendly*, jamais
*deep* ni *authoritative*.

À tester dans cet ordre, une génération chacune :

**Piste A — silence encadré** (la plus prometteuse : exploite les pauses)

- Style : `spoken word announcement, a cappella, no instruments, dry close-mic voice`

```
[1second]
[Spoken, warm friendly announcer, close mic, no music]
"On Channel Sixteen."
[1second]
```

**Piste B — a cappella assumé**

- Style : `a cappella spoken word, single warm voice, no drums, no melody, no bass`

```
[1second]
[Spoken, bright and warm, unhurried]
"On Channel Sixteen."
[1second]
```

**Piste C — audio trouvé** (le « sans musique » devient un genre, plus une négation)

- Style : `voice memo, mono intercom announcement, narrow band radio, faint tape hiss`

```
[0.5seconds]
[Spoken, warm voice through a small speaker]
"On Channel Sixteen."
[0.5seconds]
```

**Piste D — sting court assumé.** Si Suno insiste pour mettre de la musique, autant qu'elle
soit voulue : un stab d'une seconde puis la voix, c'est un tag radio parfaitement légitime.

- Style : `radio station ID, one short bright synth stab then voice, minimal, warm`

```
[Sound FX: one short bright synth stab]
[0.5seconds]
[Spoken, warm confident announcer]
"On Channel Sixteen."
```

**Piste E — version chantée.** C'est le point fort réel de Suno, et le tag chanté à trois
notes est la signature radio classique. Si A à D échouent, celle-ci a les meilleures
chances de sortir quelque chose d'utilisable — et probablement plus mémorable qu'une voix
parlée.

- Style : `sung radio station ID, three note vocal hook, bright warm harmony, light pad`

```
[Sung, bright three-note hook, warm and confident]
"On Channel Six-teen."
```

**Dans tous les cas, on découpe ensuite.** Peu importe ce que Suno rend autour : la phrase
est isolée par du silence, donc la coupe est propre.

```bash
ffmpeg -i "On Channel Sixteen.mp3" -ss 0.9 -to 2.4 -af "highpass=f=300,lowpass=f=3000,acompressor=ratio=4:threshold=-18dB,volume=4dB" -b:a 192k "tag.mp3"
```

Ajuster `-ss` / `-to` par essais successifs. Le `highpass`+`lowpass` **est** le filtre VHF :
posé dans ffmpeg plutôt qu'espéré de Suno, il est identique à chaque écoute et réglable.
Sur la piste E (chantée), retirer le filtre VHF — il écraserait l'harmonie.

**Repli.** Si les cinq pistes échouent, un TTS sort la phrase proprement et la même chaîne
de filtres s'applique. Dans tous les cas le tag est produit **une seule fois** : c'est tout
l'intérêt.

### Collage et normalisation

`ffmpeg` n'est toujours pas dans le PATH — à installer avant tout le reste.

```bash
ffmpeg -i "jingle.mp3" -i "tag.mp3" -filter_complex "[0:a][1:a]concat=n=2:v=0:a=1,loudnorm=I=-16:TP=-1.5:LRA=11" -b:a 192k "out.mp3"
```

### Si Suno refuse un jingle (« lyrics contain copyrighted material »)

Le filtre de Suno compare le champ **Lyrics** à un corpus de paroles connues. Il se
déclenche sur du texte qui *ressemble* à une chanson, pas seulement sur une citation —
d'où des faux positifs sur de la voix off. Deux formes le déclenchent ici :

- **une phrase répétée à l'identique**, qui se lit comme un refrain. C'est le piège de la
  phraséologie VHF authentique : « Mayday, mayday », « radio check, radio check »,
  « all stations, all stations ». Les 50 scripts ont été relus le 2026-09-07 pour casser
  ces doublages tout en gardant le ton procédural (« Station calling. Radio check. Do you
  read? » plutôt que le doublage littéral).
- **un idiome de parolier** : *loud and clear*, *going down*, *man overboard*, *all night*,
  *you and me*, *take it*. Retirés du lot.

Si un jingle passe quand même en refus, dans l'ordre :

1. Couper en deux la réplique la plus longue.
2. Remplacer le mot le plus « chanson » par un synonyme technique (le jargon maritime réel
   est le meilleur allié : *strength five*, *all sea areas*, *port side*, *stand by*).
3. Retirer une répétition restante.
4. En dernier recours, régénérer tel quel : le filtre n'est pas parfaitement déterministe.

Convention de nommage : `CH16 - NN - Titre.mp3`. Garder **`CH16` dans le titre ID3** de
chaque clip — c'est le marqueur qui a manqué chez Kalbass, où la détection avait dû se
rabattre sur la chaîne « kalbass fm ».

---

# A — Procédure radio VHF

## 01 — Radio Check

- Style Suno : `radio imaging, spoken word, VHF static, deep house bed, 14s`
- Durée cible : 14 s

```
[Sound FX: VHF squelch crackle, single carrier beep]
[0.5seconds]
[Spoken, flat professional radio operator]
"Station calling. Radio check. Do you read?"
[Sound FX: squelch breaks, a house beat bleeds through]
[0.5seconds]
[Spoken, same voice, warmer now]
"...received."
[0.5seconds]
"Strength five."
[0.5seconds]
"And roughly a hundred and twenty-four beats per minute."
[Outro: beat locks in, hard cut]
```

## 02 — Say Again

- Style Suno : `radio imaging, spoken word, heavy static to clean, house, 15s`
- Durée cible : 15 s

```
[Sound FX: heavy static, distant engine noise]
[0.5seconds]
[Spoken, badly garbled distorted caller]
"...ssshhh... best station... ssshh... it's free..."
[Spoken, patient operator]
"Say again? You're breaking up."
[Sound FX: static clears instantly, clean beat underneath]
[0.5seconds]
[Spoken, caller, crystal clear and delighted]
"I said I'm not changing the frequency."
[Outro: kick drops, hard cut]
```

## 03 — Over And Out

- Style Suno : `radio imaging, comedy spoken word, buzzer sting, house, 18s`
- Durée cible : 18 s

```
[Sound FX: crisp radio click]
[0.5seconds]
[Spoken, eager rookie voice]
"Great tune! Over and out!"
[Sound FX: disapproving buzzer]
[0.5seconds]
[Spoken, weary veteran operator]
"It is 'over' OR 'out'."
[0.5seconds]
"Never both."
[0.5seconds]
"Forty years I have been saying this."
[Sound FX: click]
[0.5seconds]
[Spoken, rookie, cheerfully ignoring him]
"...out."
[0.5seconds]
"And also over!"
[Outro: veteran sighs, beat kicks in]
```

## 04 — Roger That

- Style Suno : `radio imaging, rhythmic spoken word, radio clicks on beat, house, 16s`
- Durée cible : 16 s

```
[Sound FX: sharp radio click]
[0.5seconds]
[Spoken, brisk operator]
"Request received."
[0.5seconds]
"Roger."
[Sound FX: click]
[0.5seconds]
[Spoken]
"Turn it up? Roger."
[Sound FX: click]
[0.5seconds]
[Spoken]
"Until sunrise? ...Roger."
[Sound FX: click, beat swells underneath]
[0.5seconds]
[Spoken, finally cracking]
"Rogering that one twice."
[Outro: beat kicks, hard cut]
```

## 05 — Switch To Working Channel

- Style Suno : `radio imaging, spoken word, VHF hail tone, warm bassline, 14s`
- Durée cible : 14 s

```
[Sound FX: formal VHF hail tone]
[0.5seconds]
[Spoken, crisp harbour operator]
"Station calling, switch to a working channel, please."
[Sound FX: dial click, then a wall of warm bass]
[0.5seconds]
[Spoken, same voice, completely relaxed now]
"...actually, belay that."
[0.5seconds]
"The party is on this one."
[Outro: bass swells, hard cut]
```

## 06 — Securité Securité

- Style Suno : `radio imaging, deadpan announcement, maritime safety tones, sub bass, 18s`
- Durée cible : 18 s

```
[Sound FX: three formal maritime safety tones]
[0.5seconds]
[Spoken, deadpan maritime broadcaster, completely flat]
"Sécurité, sécurité, sécurité."
[0.5seconds]
"All stations, listen up."
[Sound FX: low tension pad]
[0.5seconds]
[Spoken, same flat delivery]
"Bass levels are rising in all sea areas."
[0.5seconds]
"There is nowhere left to shelter."
[Outro: sub-bass swells, hard cut to beat]
```

## 07 — Break Break

- Style Suno : `radio imaging, spoken word, comedy sting, deep house bed, 14s`
- Durée cible : 14 s

```
[Sound FX: urgent VHF squelch break, tense sting]
[0.5seconds]
[Spoken, clipped emergency-operator voice]
"Break, break — we have a situation."
[Sound FX: beat drops out completely, dead silence]
[0.5seconds]
[Spoken, same voice, deadly serious]
"Somebody played a bad song."
[0.5seconds]
"Stand by."
[Outro: correct beat slams back in, relieved exhale]
```

## 08 — Test Transmission

- Style Suno : `radio imaging, spoken word, test tone morphing into bassline, house, 16s`
- Durée cible : 16 s

```
[Sound FX: steady 1kHz test tone]
[0.5seconds]
[Spoken, bored studio engineer]
"Test transmission."
[0.5seconds]
"One."
[0.5seconds]
"Two."
[0.5seconds]
"Testing."
[Sound FX: the tone starts wobbling, turning into a bassline]
[0.5seconds]
[Spoken, engineer, losing the fight]
"Three, four... one two three four—"
[Outro: full beat explodes, engineer whoops]
```

---

# B — Détresse et garde-côtes

## 09 — Mayday But Fine

- Style Suno : `radio imaging, spoken word, alarm klaxon, fat bassline drop, 14s`
- Durée cible : 14 s

```
[Sound FX: alarm klaxon, waves crashing]
[0.5seconds]
[Spoken, panicked voice]
"Mayday! This vessel is going under!"
[Sound FX: klaxon cuts dead, a fat bassline drops]
[0.5seconds]
[Spoken, same voice, entirely calm]
"...under."
[0.5seconds]
"Like the bassline."
[0.5seconds]
"We are fine. Everyone is fine."
[Outro: bassline resolves, hard cut]
```

## 10 — Man Overboard

- Style Suno : `radio imaging, spoken word, splash and whistle, groovy house, 14s`
- Durée cible : 14 s

```
[Sound FX: splash, whistle, shouting crew]
[0.5seconds]
[Spoken, urgent first mate]
"Crew in the water! Port side!"
[Sound FX: a beat surfaces, muffled then clear]
[0.5seconds]
[Spoken, second crew member, entirely unbothered]
"He is not in trouble."
[0.5seconds]
"He is in the groove."
[0.5seconds]
"Leave him."
[Outro: groove locks in, hard cut]
```

## 11 — Coast Guard Reply

- Style Suno : `radio imaging, deadpan comedy dialogue, VHF procedure, house, 20s`
- Durée cible : 20 s

```
[Sound FX: formal VHF hail, procedural]
[0.5seconds]
[Spoken, caller, breathless]
"Coast Guard, come in — this music is unbelievable!"
[Sound FX: long pause, squelch]
[0.5seconds]
[Spoken, coast guard officer, utterly deadpan]
"Sir."
[0.5seconds]
"Excellent taste is not a maritime emergency."
[0.5seconds]
"Please stop calling."
[Sound FX: click]
[0.5seconds]
[Spoken, officer, quietly, half off-mic]
"...what station is that, though."
[Outro: beat kicks in]
```

## 12 — Abandon Ship

- Style Suno : `radio imaging, spoken word, alarm bells, epic house build, 14s`
- Durée cible : 14 s

```
[Sound FX: alarm bells, rushing feet on deck]
[0.5seconds]
[Spoken, captain, booming]
"All hands — abandon ship!"
[Sound FX: everything stops, one lonely speaker still playing]
[0.5seconds]
[Spoken, captain, quieter and very firm]
"Take the lifeboats. Leave the cargo."
[0.5seconds]
"Bring the playlist."
[Outro: beat swells, hard cut]
```

## 13 — Distress Beacon

- Style Suno : `radio imaging, comedy dialogue, EPIRB pulse, house, 17s`
- Durée cible : 17 s

```
[Sound FX: EPIRB beacon pulse, steady and alarming]
[0.5seconds]
[Spoken, rescue coordinator, tense]
"We have a beacon activation."
[0.5seconds]
"Position confirmed."
[0.5seconds]
"State the nature of your distress."
[Sound FX: beacon stops]
[0.5seconds]
[Spoken, sheepish voice]
"...somebody unplugged the aux cable."
[Outro: beat returns triumphantly, coordinator groans]
```

## 14 — Rescue Swimmer

- Style Suno : `radio imaging, spoken word, helicopter rotors into deep house, 18s`
- Durée cible : 18 s

```
[Sound FX: helicopter rotors, winch cable, sea spray]
[0.5seconds]
[Spoken, radio-filtered pilot]
"Swimmer is in the water."
[0.5seconds]
"Do you have the survivor?"
[Sound FX: rotors fade under a warm deep house groove]
[0.5seconds]
[Spoken, rescue swimmer, extremely relaxed]
"Negative."
[0.5seconds]
"I have found a vibe."
[0.5seconds]
"I am staying down here."
[Outro: groove takes over, rotors gone]
```

---

# C — Personnages nautiques

## 15 — Old Salt

- Style Suno : `radio imaging, spoken word, creaking timbers, warm house, 18s`
- Durée cible : 18 s

```
[Sound FX: creaking timbers, pipe crackle, low swell]
[0.5seconds]
[Spoken, grizzled old sailor]
"In my day we had one channel."
[0.5seconds]
"ONE."
[0.5seconds]
"And it were all static, and we were grateful."
[Sound FX: a clean modern beat fades up underneath]
[0.5seconds]
[Spoken, softening despite himself]
"...this is better."
[0.5seconds]
"Don't tell the crew I said it."
[Outro: beat opens up, hard cut]
```

## 16 — Lighthouse Keeper

- Style Suno : `radio imaging, emotional spoken word, foghorn, melodic deep house, 19s`
- Durée cible : 19 s

```
[Sound FX: foghorn, wind, the slow hum of a rotating lamp]
[0.5seconds]
[Spoken, gentle, slightly stir-crazy]
"Forty years I have kept this light."
[0.5seconds]
"Four decades of wind, gulls, and my own voice."
[Sound FX: a radio clicks on, warm music]
[0.5seconds]
[Spoken, genuinely moved]
"And now there is someone on the other end."
[0.5seconds]
"Every night."
[Outro: music blooms, foghorn answers on the beat]
```

## 17 — Harbourmaster

- Style Suno : `radio imaging, spoken word, harbour bell, tech house, 14s`
- Durée cible : 14 s

```
[Sound FX: harbour bell, ropes, gulls]
[0.5seconds]
[Spoken, brisk administrative voice]
"Vessel inbound — you are assigned berth fourteen, portside."
[Sound FX: rubber stamp thud]
[0.5seconds]
[Spoken, same tone, no change whatsoever]
"And a hundred and twenty-two beats per minute."
[0.5seconds]
"Mind the swell."
[Outro: beat starts exactly on tempo, hard cut]
```

## 18 — Ferry Announcer

- Style Suno : `radio imaging, comedy spoken word, tannoy chime, big house drop, 14s`
- Durée cible : 14 s

```
[Sound FX: tannoy chime, ferry engine drone]
[0.5seconds]
[Spoken, catastrophically bored PA voice]
"The vehicle deck is now closed."
[0.5seconds]
"Passengers please remain seated."
[Sound FX: tannoy chime again]
[0.5seconds]
[Spoken, same voice, suddenly fully alive]
"AND THE BASS DECK IS NOW OPEN!"
[Outro: beat explodes, engine drone becomes the sub]
```

## 19 — The Lost Sailor

- Style Suno : `radio imaging, cinematic spoken word, sparse to full bassline, 19s`
- Durée cible : 19 s

```
[Sound FX: creaking hull, empty wind, no instruments at all]
[0.5seconds]
[Spoken, tired, drifting]
"No stars."
[0.5seconds]
"No GPS."
[0.5seconds]
"No idea where I am."
[Sound FX: a distant bassline, growing]
[0.5seconds]
[Spoken, waking up]
"But I can hear it."
[0.5seconds]
"And it is getting louder."
[0.5seconds]
"That is east. That is home."
[Outro: bassline arrives full, hard cut]
```

## 20 — Mermaid

- Style Suno : `radio imaging, sardonic spoken word, underwater shimmer, house, 17s`
- Durée cible : 17 s

```
[Sound FX: underwater shimmer, bubbles, dreamy harp]
[0.5seconds]
[Spoken, sardonic mermaid]
"Two thousand years I have lured sailors with my singing."
[Sound FX: a beat kicks in from above the surface]
[0.5seconds]
[Spoken, deeply unimpressed]
"Now they swim straight past me toward the radio."
[0.5seconds]
"Fine."
[0.5seconds]
"Honestly — fair."
[Outro: beat swells, harp gives up]
```

## 21 — Kraken

- Style Suno : `radio imaging, colossal slow spoken word, deep dub, sonar, 20s`
- Durée cible : 20 s

```
[Sound FX: immense low groan, deep water pressure, distant sonar]
[0.5seconds]
[Spoken, colossal, slow, surprisingly gentle]
"For a thousand years I have slept in the dark and the cold."
[Sound FX: a slow dub bassline unfurls]
[0.5seconds]
[Spoken, contented rumble]
"Do not wake me."
[0.5seconds]
"Unless it is for the dub."
[0.5seconds]
"Then wake me."
[Outro: dub delay trails off, hard cut]
```

## 22 — Seagull Interruption

- Style Suno : `radio imaging, comedy chaos, seaside ambience, house, 17s`
- Durée cible : 17 s

```
[Sound FX: seaside ambience, gulls]
[0.5seconds]
[Spoken, smooth professional announcer]
"You are listening to the finest selection on the water, brought to you by—"
[Sound FX: violent gull screech, microphone knocked over, chaos]
[0.5seconds]
[Spoken, announcer, from much further away, defeated]
"—he has got the microphone."
[0.5seconds]
"He thinks it is a chip."
[0.5seconds]
"Just play the record."
[Outro: beat kicks in over triumphant squawking]
```

---

# D — Absurdes transposés en mer

## 23 — Alien On 16

- Style Suno : `radio imaging, comedy alien voice, UFO blips, house, 16s`
- Durée cible : 16 s

```
[Sound FX: comedic UFO whirr, cartoon scanning blips]
[0.5seconds]
[Spoken, squeaky curious alien voice]
"Scanning the distress frequencies of planet Earth."
[0.5seconds]
"Detecting... a party?"
[Sound FX: confused blip]
[0.5seconds]
[Spoken, delighted]
"This is the emergency channel."
[0.5seconds]
"These humans are magnificent."
[0.5seconds]
"I am landing."
[Outro: landing gear thud, beat kicks in]
```

## 24 — Grandma At Sea

- Style Suno : `radio imaging, warm comedy spoken word, ferry lounge, cosy house, 16s`
- Durée cible : 16 s

```
[Sound FX: cosy ferry lounge, teacup rattle, gentle swell]
[0.5seconds]
[Spoken, warm grandma voice, mildly confused but genuinely into it]
"Ooh, the boat is doing that wobble again."
[0.5seconds]
"And so is the music, dear."
[Sound FX: gentle chime]
[0.5seconds]
[Spoken]
"No adverts, they said."
[0.5seconds]
"Well, isn't that lovely."
[0.5seconds]
"Pass the biscuits."
[Outro: teacup rattles on the beat, hard cut]
```

## 25 — Two Robots, One Channel

- Style Suno : `radio imaging, robot voices, glitch beeps, electro house, 18s`
- Durée cible : 18 s

```
[Sound FX: two units powering up, glitch beeps]
[0.5seconds]
[Spoken, robot voice one, flat]
"I will announce the station."
[Spoken, robot voice two, overlapping]
"Negative."
[0.5seconds]
"I will announce the station."
[Spoken, both colliding]
"I WILL ANNOUNCE THE—"
[Sound FX: mutual system crash, sad descending beep]
[0.5seconds]
[Spoken, robot voice three, tiny and smug]
"...I will announce the station."
[Outro: beat kicks in]
```

## 26 — Game Show Overboard

- Style Suno : `radio imaging, game show host, drumroll and confetti, house, 16s`
- Durée cible : 16 s

```
[Sound FX: dramatic drumroll, studio audience]
[0.5seconds]
[Spoken, booming game show host]
"And tonight's grand prize... is a FREQUENCY!"
[Sound FX: confetti cannon, cheering, then a single confused clap]
[0.5seconds]
[Spoken, host, entirely undeterred]
"Unlike every other game show — everyone wins."
[0.5seconds]
"Every night."
[0.5seconds]
"For nothing."
[Outro: triumphant sting, hard cut to beat]
```

## 27 — Drive-Thru Marina

- Style Suno : `radio imaging, tinny intercom voice, water lapping, house, 14s`
- Durée cible : 14 s

```
[Sound FX: crackly intercom static, water lapping, distant kitchen clatter]
[0.5seconds]
[Spoken, tinny distorted intercom voice]
"Hi, welcome to the marina, can I take your request?"
[Sound FX: comedic beep]
[0.5seconds]
[Spoken]
"That will be zero euros."
[0.5seconds]
"Pull around to the pontoon and mind the bassline."
[Outro: intercom clicks off, beat kicks in]
```

## 28 — Yoga On The Foredeck

- Style Suno : `radio imaging, serene voice turning feral, meditation chime, house, 16s`
- Durée cible : 16 s

```
[Sound FX: calm sea, soft meditation chime, distant gulls]
[0.5seconds]
[Spoken, soothing yoga instructor, very serene]
"Feel the deck beneath you."
[0.5seconds]
"Breathe in the salt air... and breathe out..."
[Sound FX: sudden record scratch]
[0.5seconds]
[Spoken, same voice, now completely feral]
"...INTO THE BASSLINE."
[0.5seconds]
"Namaste."
[0.5seconds]
"Now dance, before we capsize."
[Outro: beat slams in, chime shatters]
```

## 29 — Elevator To The Bridge

- Style Suno : `radio imaging, elevator muzak morphing into house, comedy, 16s`
- Durée cible : 16 s

```
[Sound FX: cheesy smooth elevator muzak, gentle chime]
[0.5seconds]
[Spoken, bored elevator announcer]
"Engine room."
[0.5seconds]
"Going up."
[Sound FX: ding]
[0.5seconds]
[Spoken]
"Galley."
[0.5seconds]
"Going up."
[Sound FX: glass shatter, dramatic sting]
[0.5seconds]
[Spoken, suddenly ecstatic]
"BRIDGE! And we are going ALL the way up!"
[Outro: muzak morphs into full house beat]
```

## 30 — Infomercial: Free Frequency

- Style Suno : `radio imaging, cheesy infomercial salesman, jingle bells, house, 18s`
- Durée cible : 18 s

```
[Sound FX: cheesy infomercial jingle bell]
[0.5seconds]
[Spoken, hyped-up salesman voice]
"Tired of paying for music? STOP paying — because this frequency is FREE! No subscription! No adverts! No catch!"
[Sound FX: cash register cha-ching, reversed into a laugh]
[0.5seconds]
[Spoken]
"Call now! Wait — you cannot call a radio station."
[0.5seconds]
"Just... do not touch the dial."
[Outro: cheesy sting, hard cut to beat]
```

## 31 — Off-Key Karaoke

- Style Suno : `radio imaging, deliberately off-key singing, cruise lounge, house, 17s`
- Durée cible : 17 s

```
[Sound FX: karaoke intro chime, cruise ship lounge ambience]
[0.5seconds]
[Sung, gloriously off-key and wobbly]
"Chaaaa-nnel... siiiix... teeeee—"
[Sound FX: record scratch, one person laughing]
[0.5seconds]
[Spoken, normal voice, recovering with dignity]
"...right."
[0.5seconds]
"Let us leave the singing to the professionals."
[0.5seconds]
"Free music, no adverts."
[Outro: clean beat kicks in]
```

## 32 — PSA: Unauthorized Dancing

- Style Suno : `radio imaging, deadpan PSA voice, mock-serious sting, house, 19s`
- Durée cible : 19 s

```
[Sound FX: mock-serious PSA jingle sting]
[0.5seconds]
[Spoken, deadpan public information voice]
"This has been a public service announcement."
[0.5seconds]
"Unauthorized dancing may occur aboard this vessel."
[Sound FX: single comedic beep]
[0.5seconds]
[Spoken]
"We are not liable for spontaneous good moods."
[0.5seconds]
"Listener discretion is NOT advised."
[Outro: deadpan sting resolves into beat]
```

---

# E — Météo marine

## 33 — Shipping Forecast

- Style Suno : `radio imaging, hypnotic shipping forecast voice, solemn chime, deep house, 19s`
- Durée cible : 19 s

```
[Sound FX: the familiar solemn forecast chime, gentle static]
[0.5seconds]
[Spoken, hypnotic shipping-forecast voice, entirely unhurried]
"Dogger."
[0.5seconds]
"Fisher."
[0.5seconds]
"German Bight."
[0.5seconds]
"Southwesterly, four to five."
[Sound FX: a beat creeps in underneath, almost politely]
[0.5seconds]
[Spoken, same hypnotic calm]
"Bass: imminent. Occasionally severe."
[0.5seconds]
"Good."
[Outro: beat takes the room, chime answers]
```

## 34 — Gale Warning

- Style Suno : `radio imaging, urgent forecaster, rising wind, big drop, 18s`
- Durée cible : 18 s

```
[Sound FX: rising wind, rigging clatter, warning tone]
[0.5seconds]
[Spoken, urgent forecaster]
"Gale warning."
[0.5seconds]
"Severe conditions, all sea areas."
[0.5seconds]
"Seek shelter immediately."
[Sound FX: wind drops out abruptly]
[0.5seconds]
[Spoken, dropping the act entirely]
"...it is not weather."
[0.5seconds]
"It is the drop."
[0.5seconds]
"Nothing you can do."
[0.5seconds]
"Enjoy it."
[Outro: the drop lands, hard cut]
```

## 35 — Sea State

- Style Suno : `radio imaging, measured spoken word, buoy bell, funky house, 15s`
- Durée cible : 15 s

```
[Sound FX: gentle swell, buoy bell]
[0.5seconds]
[Spoken, measured maritime observer]
"Sea state: moderate."
[0.5seconds]
"Wave height: one to two metres."
[Sound FX: the swell locks into a rhythm]
[0.5seconds]
[Spoken, same measured tone, entirely unbothered]
"Sea state: becoming funky."
[0.5seconds]
"Wave height: irrelevant."
[Outro: groove locks, buoy bell on the offbeat]
```

## 36 — Visibility

- Style Suno : `radio imaging, flat forecaster, dense fog, crisp beat cutting through, 16s`
- Durée cible : 16 s

```
[Sound FX: dense fog, distant foghorn, everything muffled]
[0.5seconds]
[Spoken, forecaster, flat]
"Visibility: poor."
[0.5seconds]
"Fog patches."
[0.5seconds]
"Two hundred metres and falling."
[Sound FX: the fog stays, but a crisp beat cuts straight through it]
[0.5seconds]
[Spoken]
"Sound quality: excellent."
[0.5seconds]
"You do not need to see where you are going."
[Outro: beat carries on through the fog]
```

## 37 — Tide Table

- Style Suno : `radio imaging, patient spoken word, rising water into filter sweep, house, 18s`
- Durée cible : 18 s

```
[Sound FX: water rising against a harbour wall, slow]
[0.5seconds]
[Spoken, patient tidal announcer]
"High water at four minutes past eight."
[0.5seconds]
"Springs."
[0.5seconds]
"Range: four point one metres."
[Sound FX: the rising water becomes a rising filter sweep]
[0.5seconds]
[Spoken]
"The tempo does the same thing."
[0.5seconds]
"Nobody has ever stopped either one."
[Outro: filter opens fully, beat lands]
```

---

# F — Instruments de bord

## 38 — Sonar Ping

- Style Suno : `radio imaging, hushed spoken word, sonar ping becoming a kick drum, 16s`
- Durée cible : 16 s

```
[Sound FX: single sonar ping, long decay, deep water]
[0.5seconds]
[Spoken, hushed sonar operator]
"Contact."
[0.5seconds]
"Bearing zero-one-six."
[0.5seconds]
"It is... rhythmic."
[Sound FX: the ping repeats, and repeats, becoming a kick drum]
[0.5seconds]
[Spoken, whispering, thrilled]
"That is not a submarine."
[0.5seconds]
"That is a four-four."
[Outro: kick fully formed, hard cut]
```

## 39 — Autopilot

- Style Suno : `radio imaging, polite synthetic voice, bridge ambience, tech house, 16s`
- Durée cible : 16 s

```
[Sound FX: calm bridge ambience, gentle system chime]
[0.5seconds]
[Spoken, polite synthetic voice]
"Autopilot engaged."
[0.5seconds]
"Heading zero-one-six."
[0.5seconds]
"Please do not adjust."
[Sound FX: a hand reaching for a dial, a warning beep]
[0.5seconds]
[Spoken, same politeness, now faintly menacing]
"I said please do not adjust."
[0.5seconds]
"We are not changing the station."
[Outro: system chime resolves into beat]
```

## 40 — Depth Sounder

- Style Suno : `radio imaging, spoken word, echo sounder pulse, heavy dub, 18s`
- Durée cible : 18 s

```
[Sound FX: echo sounder pulse, deep resonant returns]
[0.5seconds]
[Spoken, crew member reading the display]
"Depth: forty metres."
[0.5seconds]
"Sixty."
[0.5seconds]
"Ninety."
[Sound FX: the returns get lower and warmer]
[0.5seconds]
[Spoken, quietly]
"Depth: too deep to measure."
[0.5seconds]
"It is dub."
[0.5seconds]
"Obviously it is dub."
[Outro: dub delay swallows the pulse]
```

## 41 — Ship's Computer

- Style Suno : `radio imaging, polite passive-aggressive AI voice, server hum, warm house, 19s`
- Durée cible : 19 s

```
[Sound FX: server hum, soft interface tones]
[0.5seconds]
[Spoken, impeccably polite ship's computer, faintly passive-aggressive]
"Good evening."
[0.5seconds]
"All systems nominal."
[0.5seconds]
"Fuel: adequate."
[0.5seconds]
"Morale: historically low."
[Sound FX: a warm chord fades up]
[0.5seconds]
[Spoken]
"I have taken the liberty of fixing the last one myself."
[0.5seconds]
"You are welcome."
[Outro: full track blooms, interface tones land on the beat]
```

## 42 — GPS Recalculating

- Style Suno : `radio imaging, flat satnav voice turning warm, nav beeps, house, 16s`
- Durée cible : 16 s

```
[Sound FX: satellite lock beep, navigation interface]
[0.5seconds]
[Spoken, flat satnav voice]
"Recalculating."
[0.5seconds]
"Recalculating."
[0.5seconds]
"Route unavailable."
[Sound FX: beat fades up, confident]
[0.5seconds]
[Spoken, satnav, unexpectedly warm]
"Correction."
[0.5seconds]
"You have arrived."
[0.5seconds]
"You arrived a while ago, actually."
[Outro: beat settles, hard cut]
```

---

# G — Méta-radio

## 43 — Dead Air

- Style Suno : `radio imaging, silence then full volume, comedy panic, house, 16s`
- Durée cible : 16 s

```
[Sound FX: absolute silence. Then a chair creak. Then nothing at all.]
[1second]
[Spoken, whispered, panicking]
"...is it on? Is it on? Oh no. Oh no—"
[Sound FX: fader slams up, music at full volume]
[0.5seconds]
[Spoken, instantly professional, as though nothing happened]
"—and that was seven seconds you will never get back."
[0.5seconds]
"Neither will I."
[Outro: beat carries on, hard cut]
```

## 44 — Wrong Channel

- Style Suno : `radio imaging, dial tuning through static, beautiful chord landing, house, 14s`
- Durée cible : 14 s

```
[Sound FX: dial tuning, snatches of static and voices]
[0.5seconds]
[Spoken, mild, slightly lost listener]
"Hello? I was looking for the weather forecast."
[Sound FX: the dial stops, a beautiful chord lands]
[0.5seconds]
[Spoken, same voice, three seconds later, transformed]
"...I no longer care about the weather."
[Outro: beat opens up, hard cut]
```

## 45 — The DJ Fell Asleep

- Style Suno : `radio imaging, comedy, snoring and run-out groove, sudden house drop, 14s`
- Durée cible : 14 s

```
[Sound FX: gentle snoring, a record's run-out groove clicking round]
[1second]
[Spoken, mumbling, half asleep]
"...mmh... and that was... mmh..."
[Sound FX: violent chair scrape, papers everywhere]
[0.5seconds]
[Spoken, wide awake and far too loud]
"WE ARE LIVE! We have been live the whole time! Nobody move!"
[Outro: beat slams in]
```

## 46 — Nobody Is Watching The Channel

- Style Suno : `radio imaging, quiet sincere spoken word, ticking clock, melodic house, 18s`
- Durée cible : 18 s

```
[Sound FX: empty radio room, low hum, a clock ticking]
[0.5seconds]
[Spoken, quiet operator, talking to nobody]
"Regulations say someone must keep watch on this frequency at all times."
[Sound FX: a track fades up, warm]
[0.5seconds]
[Spoken, a small smile in the voice]
"Been doing it for years."
[0.5seconds]
"Turns out I like the company."
[Outro: track blooms, clock ticks on the beat]
```

## 47 — Always Monitoring

- Style Suno : `radio imaging, sincere late-night spoken word, night ambience, deep house, 18s`
- Durée cible : 18 s

```
[Sound FX: night ambience, distant swell, a single carrier tone]
[0.5seconds]
[Spoken, calm, steady, sincere]
"It is three in the morning."
[0.5seconds]
"Somewhere out there, someone is still awake."
[Sound FX: bass enters, patient]
[0.5seconds]
[Spoken]
"Somebody is always keeping watch on this frequency."
[0.5seconds]
"Tonight, that is you."
[Outro: bass carries, hard cut]
```

---

# H — Gratuité et valeur

## 48 — No Ads, No Fees

- Style Suno : `radio imaging, matter-of-fact spoken word, clean radio clicks, house, 16s`
- Durée cible : 16 s

```
[Sound FX: brisk radio click]
[0.5seconds]
[Spoken, matter-of-fact operator]
"No adverts."
[0.5seconds]
"No subscription."
[0.5seconds]
"No login."
[0.5seconds]
"No algorithm deciding what you like."
[Sound FX: single clean beep]
[0.5seconds]
[Spoken]
"Just a frequency, and whoever is brave enough to be on it."
[Outro: beat kicks in, hard cut]
```

## 49 — Licence Free

- Style Suno : `radio imaging, bureaucratic voice turning warm, paper and stamps, house, 16s`
- Durée cible : 16 s

```
[Sound FX: officious paper shuffle, rubber stamp]
[0.5seconds]
[Spoken, bureaucratic voice]
"To transmit on this frequency you require a licence, a callsign, and an examination."
[Sound FX: stamp thud, then all the papers scatter]
[0.5seconds]
[Spoken, warmly]
"To LISTEN, you require nothing at all."
[0.5seconds]
"You never have."
[Outro: beat kicks in over scattering paper]
```

## 50 — Zero Dollars

- Style Suno : `radio imaging, comedy cashier voice, cash register, cheerful house, 18s`
- Durée cible : 18 s

```
[Sound FX: cash register opening, then a long confused pause]
[1second]
[Spoken, cashier voice, checking the total twice]
"That comes to... zero."
[0.5seconds]
"Zero euros."
[0.5seconds]
"Zero dollars."
[0.5seconds]
"Zero of anything."
[Sound FX: register drawer slams shut, cheerful]
[0.5seconds]
[Spoken]
"Go on. It is yours."
[0.5seconds]
"The whole night."
[Outro: beat kicks in]
```

---

# I — Plein soleil

## 51 — Sun Is Out

- Style Suno : `radio imaging, bright spoken word, balearic house, gulls, 12s`
- Durée cible : 12 s

```
[Sound FX: bright morning gulls, water slapping a hull]
[0.5seconds]
[Spoken, cheerful forecaster, smiling audibly]
"Forecast for today: sun."
[0.5seconds]
"Tomorrow: also sun."
[Sound FX: a warm balearic chord opens up]
[0.5seconds]
[Spoken, same bright voice]
"Honestly, we stopped checking."
[0.5seconds]
"Go outside."
[Outro: sunny groove lands, hard cut]
```

## 52 — Factor Fifty

- Style Suno : `radio imaging, bright public-service voice, beach ambience, sunny house, 15s`
- Durée cible : 15 s

```
[Sound FX: cheerful PSA chime, beach ambience]
[0.5seconds]
[Spoken, bright and helpful public-service voice]
"A friendly reminder from your local frequency."
[0.5seconds]
"Factor fifty."
[Sound FX: comedic squirt of sunscreen, a small laugh]
[0.5seconds]
[Spoken, warm]
"We can play you music all afternoon."
[0.5seconds]
"We cannot un-burn your shoulders."
[Outro: bright groove kicks in]
```

## 53 — Barefoot On Deck

- Style Suno : `radio imaging, relaxed sunny voice, light disco bassline, 13s`
- Durée cible : 13 s

```
[Sound FX: bare feet on warm wood, gentle swell]
[0.5seconds]
[Spoken, relaxed sunny voice, half-smiling]
"Shoes off."
[0.5seconds]
"Deck is warm."
[0.5seconds]
"That is the whole dress code."
[Sound FX: a light disco bassline slides in]
[0.5seconds]
[Spoken]
"Everything else is optional."
[Outro: bassline opens, hard cut]
```

## 54 — Ice In The Cooler

- Style Suno : `radio imaging, delighted spoken word, summer groove, ice and fizz, 16s`
- Durée cible : 16 s

```
[Sound FX: cooler lid opening, ice clinking, the fizz of a bottle]
[0.5seconds]
[Spoken, delighted, sun-drunk]
"There is still ice in the cooler."
[0.5seconds]
"Do you understand what that means?"
[Sound FX: bottle cap pops, a cheerful whoop]
[0.5seconds]
[Spoken, laughing]
"It means nobody has to go back to shore yet."
[Outro: summer groove kicks in]
```

## 55 — Golden Hour

- Style Suno : `radio imaging, soft glowing spoken word, warm melodic house, evening, 15s`
- Durée cible : 15 s

```
[Sound FX: evening gulls, the water going quiet, warm still air]
[0.5seconds]
[Spoken, soft and glowing, unhurried]
"The light has gone gold."
[0.5seconds]
"It does this for about forty minutes."
[Sound FX: a warm chord blooms]
[0.5seconds]
[Spoken, gently]
"We have got the soundtrack ready."
[0.5seconds]
"Look west."
[Outro: chord resolves, beat lands]
```

## 56 — The Sea Is Warm

- Style Suno : `radio imaging, breathless happy voices, splashes, bright house, 15s`
- Durée cible : 15 s

```
[Sound FX: a body hitting the water, laughter, splash]
[0.5seconds]
[Spoken, breathless and happy, treading water]
"It is warm! Everyone — it is actually warm!"
[Sound FX: three more splashes in quick succession]
[0.5seconds]
[Spoken, from the deck, amused]
"...and that is the entire crew overboard."
[0.5seconds]
"Nobody is coming back up here."
[Outro: bright groove takes over]
```

## 57 — Nothing To Do Today

- Style Suno : `radio imaging, blissful spoken word, hammock, easy groove, 12s`
- Durée cible : 12 s

```
[Sound FX: a hammock creaking, distant gulls]
[0.5seconds]
[Spoken, blissfully unbothered]
"Let me read you today's schedule."
[Sound FX: paper unfolding, then stopping]
[0.5seconds]
[Spoken, brightly]
"It is blank."
[0.5seconds]
"It has been blank all week."
[Outro: easy groove drifts in, hard cut]
```

## 58 — Sunrise Watch

- Style Suno : `radio imaging, warm awake voice, dawn ambience, uplifting house, 10s`
- Durée cible : 10 s

```
[Sound FX: very early quiet, one gull, water lapping]
[0.5seconds]
[Spoken, warm and awake, a little proud]
"Everybody else is asleep."
[0.5seconds]
"The sun is not."
[Sound FX: a bright chord rises with it]
[0.5seconds]
[Spoken, smiling]
"Neither are we."
[Outro: chord opens into a beat, hard cut]
```

---

# J — Passagers et vacanciers

## 59 — First Time At Sea

- Style Suno : `radio imaging, thrilled young voice, ferry engine, bright house, 14s`
- Durée cible : 14 s

```
[Sound FX: ferry engine, excited chatter]
[0.5seconds]
[Spoken, thrilled young voice]
"That is the actual sea!"
[0.5seconds]
"It goes all the way to the edge!"
[Sound FX: gentle chime, an adult laughing softly]
[0.5seconds]
[Spoken, warm adult voice]
"It does. And it has a soundtrack."
[Outro: bright groove kicks in]
```

## 60 — The Tourist

- Style Suno : `radio imaging, cheerful comedy dialogue, seaside, sunny house, 13s`
- Durée cible : 13 s

```
[Sound FX: seaside ambience, a camera shutter]
[0.5seconds]
[Spoken, enthusiastic visitor, cheerfully lost]
"Excuse me — which way is the beach?"
[Sound FX: a pause, one gull]
[0.5seconds]
[Spoken, patient local voice, amused]
"Sir. You are standing on it."
[0.5seconds]
"Put the map down."
[Outro: sunny beat kicks in]
```

## 61 — Are We There Yet

- Style Suno : `radio imaging, kid and parent, ferry hum, bright groove, 14s`
- Durée cible : 14 s

```
[Sound FX: ferry hum, a kid fidgeting]
[0.5seconds]
[Spoken, small impatient voice]
"Are we there yet?"
[Sound FX: gentle chime]
[0.5seconds]
[Spoken, easy-going parent]
"No."
[0.5seconds]
"But the music is good and the sun is out."
[0.5seconds]
"So technically, yes."
[Outro: bright groove lands]
```

## 62 — Holiday Brain

- Style Suno : `radio imaging, pleasantly confused voices, waves, easy beat, 11s`
- Durée cible : 11 s

```
[Sound FX: gentle waves, a page turning]
[0.5seconds]
[Spoken, pleasantly confused, very relaxed]
"What day is it?"
[Sound FX: a long gull cry]
[0.5seconds]
[Spoken, equally relaxed, from a deckchair]
"No idea."
[0.5seconds]
"That is usually a good sign."
[Outro: easy beat drifts in, hard cut]
```

## 63 — Postcard Home

- Style Suno : `radio imaging, breezy dictation voice, cafe clatter, sunny groove, 13s`
- Durée cible : 13 s

```
[Sound FX: a pen scratching, cafe clatter, gulls]
[0.5seconds]
[Spoken, bright and breezy, dictating]
"Dear everyone. Weather: excellent."
[0.5seconds]
"Food: excellent."
[Sound FX: the pen stops, a small happy sigh]
[0.5seconds]
[Spoken]
"Also there is a radio station out here."
[0.5seconds]
"Not coming back."
[Outro: sunny groove kicks in]
```

## 64 — The Inflatable Flamingo

- Style Suno : `radio imaging, playful harbour announcement, squeaky inflatable, fun house, 15s`
- Durée cible : 15 s

```
[Sound FX: squeaky inflatable, water, laughing]
[0.5seconds]
[Spoken, cheerful harbour announcer, trying to stay official]
"Attention: an unregistered pink vessel has entered the marina."
[Sound FX: a comedic squeak]
[0.5seconds]
[Spoken, giving up immediately]
"It has no engine, no lights, and no plans."
[0.5seconds]
"Honestly, we respect it."
[Outro: playful groove kicks in]
```

## 65 — Sandy Feet

- Style Suno : `radio imaging, warm unbothered voice, jetty footsteps, bright house, 16s`
- Durée cible : 16 s

```
[Sound FX: footsteps on a wooden jetty, sand brushing off]
[0.5seconds]
[Spoken, warm and unbothered]
"There is sand in the cabin. There is sand in the galley."
[Sound FX: more sand, a small laugh]
[0.5seconds]
[Spoken]
"There is sand in places I will not describe on air."
[0.5seconds]
"Worth it."
[Outro: bright beat kicks in]
```

---

# K — Vie du port

## 66 — The Fish Market

- Style Suno : `radio imaging, bright market trader, busy market, lively house, 15s`
- Durée cible : 15 s

```
[Sound FX: busy market, ice being shovelled, cheerful shouting]
[0.5seconds]
[Spoken, bright market trader, full of morning energy]
"Fresh this morning! Straight off the boat!"
[Sound FX: a crate thumps down, ice clatters]
[0.5seconds]
[Spoken, same voice, conspiratorial and warm]
"And the radio is on all day."
[0.5seconds]
"That is why the queue is this long."
[Outro: lively groove kicks in]
```

## 67 — Cafe On The Quay

- Style Suno : `radio imaging, friendly warm voice, espresso machine, warm groove, 13s`
- Durée cible : 13 s

```
[Sound FX: espresso machine, cups, morning chatter]
[0.5seconds]
[Spoken, friendly cafe voice]
"One coffee. Outside table. Sun on your face."
[Sound FX: a cup set down on a saucer]
[0.5seconds]
[Spoken, warmly]
"The music comes free with it."
[0.5seconds]
"It always has."
[Outro: warm groove kicks in]
```

## 68 — The Ice Cream Boat

- Style Suno : `radio imaging, delighted child and cheerful vendor, chime, playful house, 13s`
- Durée cible : 13 s

```
[Sound FX: a tinny ice cream chime, but out on the water]
[0.5seconds]
[Spoken, delighted child]
"There is a boat! And it sells ICE CREAM!"
[Sound FX: an outboard motor puttering closer, the chime again]
[0.5seconds]
[Spoken, cheerful vendor]
"Two scoops, and I am not changing the station."
[Outro: bright playful beat kicks in]
```

## 69 — Harbour Cat

- Style Suno : `radio imaging, gentle amused voice, quiet quay, light groove, 16s`
- Durée cible : 16 s

```
[Sound FX: a quiet quay, ropes, a contented cat]
[0.5seconds]
[Spoken, gentle amused voice]
"This cat belongs to no one."
[0.5seconds]
"He inspects every boat that comes in."
[Sound FX: a soft purr, a small bell]
[0.5seconds]
[Spoken, fondly]
"He has approved this frequency."
[0.5seconds]
"That is not nothing."
[Outro: light groove kicks in]
```

## 70 — The Rope Guy

- Style Suno : `radio imaging, cheerful over-invested voice, harbour, easy beat, 16s`
- Durée cible : 16 s

```
[Sound FX: rope creaking, gentle harbour sounds]
[0.5seconds]
[Spoken, cheerful and far too invested]
"This one is a bowline. This one is a clove hitch."
[Sound FX: rope pulled taut, a satisfied little laugh]
[0.5seconds]
[Spoken, brightly]
"Nobody asked. I am telling you anyway."
[0.5seconds]
"Great music, though — right?"
[Outro: easy beat kicks in]
```

## 71 — Morning Delivery

- Style Suno : `radio imaging, wide-awake friendly voice, early quay, bright groove, 15s`
- Durée cible : 15 s

```
[Sound FX: a small van, crates, the early quiet of a quay]
[0.5seconds]
[Spoken, wide-awake and friendly, far too early]
"Bread, ice, and two crates of lemons."
[0.5seconds]
"Every morning at six."
[Sound FX: a crate set down, a stretch, a yawn]
[0.5seconds]
[Spoken, cheerfully]
"And whoever is on the radio is already awake."
[0.5seconds]
"Solidarity."
[Outro: bright groove kicks in]
```

## 72 — The Boat Mechanic

- Style Suno : `radio imaging, cheerful grease-stained voice, engine into bassline, 14s`
- Durée cible : 14 s

```
[Sound FX: a spanner on metal, an engine coughing]
[0.5seconds]
[Spoken, cheerful grease-stained voice]
"Right. She will start."
[0.5seconds]
"Probably."
[Sound FX: the engine catches and runs sweetly]
[0.5seconds]
[Spoken, delighted with himself]
"There she goes. Told you."
[0.5seconds]
"Now turn the radio up, we are celebrating."
[Outro: engine hum becomes the bassline]
```

---

# L — Petites créatures

## 73 — Dolphin Escort

- Style Suno : `radio imaging, bright delighted voice, bow wave, buoyant house, 17s`
- Durée cible : 17 s

```
[Sound FX: bow wave, excited clicks and whistles]
[0.5seconds]
[Spoken, bright and delighted]
"We have got company. Three of them, off the bow."
[Sound FX: a joyful leap, a splash, laughter on deck]
[0.5seconds]
[Spoken, laughing]
"They do this every time we come through here."
[0.5seconds]
"I like to think it is the music."
[Outro: buoyant groove kicks in]
```

## 74 — The Ship's Dog

- Style Suno : `radio imaging, warm fond voice, happy dog, cheerful beat, 16s`
- Durée cible : 16 s

```
[Sound FX: happy panting, a tail thumping on deck]
[0.5seconds]
[Spoken, warm and fond]
"He has no job. He has no rank."
[Sound FX: a single delighted bark]
[0.5seconds]
[Spoken, amused]
"He gets on the boat first and off the boat last."
[0.5seconds]
"He is doing it perfectly."
[Outro: cheerful beat kicks in]
```

## 75 — Pelican Correspondent

- Style Suno : `radio imaging, playful announcer, comedy bird, light groove, 13s`
- Durée cible : 13 s

```
[Sound FX: wings, a heavy landing on a wooden post]
[0.5seconds]
[Spoken, playful announcer]
"And now, our correspondent on the harbour wall."
[Sound FX: a long, deeply unimpressed pelican noise]
[0.5seconds]
[Spoken, brightly]
"Thank you. Insightful as always."
[0.5seconds]
"Back to the music."
[Outro: light groove kicks in]
```

## 76 — Baby Turtle

- Style Suno : `radio imaging, hushed wonder, night surf, warm uplifting house, 15s`
- Durée cible : 15 s

```
[Sound FX: soft sand, tiny flippers, gentle surf at night]
[0.5seconds]
[Spoken, hushed and smiling, full of wonder]
"Look. Look at the size of it."
[0.5seconds]
"Twenty metres to the water."
[Sound FX: a small wave arrives, a gentle cheer from the beach]
[0.5seconds]
[Spoken, delighted]
"She made it."
[0.5seconds]
"Turn it up for her."
[Outro: warm uplifting chord into the beat]
```

---

# M — Radio légère

## 77 — The Weather Is Just Fine

- Style Suno : `radio imaging, sunny forecaster, cheerful chime, bright house, 14s`
- Durée cible : 14 s

```
[Sound FX: a forecast chime, but a cheerful one]
[0.5seconds]
[Spoken, sunny forecaster]
"I have been handed the marine forecast."
[Sound FX: paper unfolds]
[0.5seconds]
[Spoken, brightening]
"It says: fine. Everywhere. All day."
[0.5seconds]
"Shortest bulletin I have ever read."
[Outro: bright groove kicks in]
```

## 78 — Wrong Button

- Style Suno : `radio imaging, cheerful self-deprecating voice, comedy sound effects, 12s`
- Durée cible : 12 s

```
[Sound FX: a click, then a completely wrong sound effect — a cow]
[0.5seconds]
[Spoken, cheerfully embarrassed]
"That was not the jingle."
[Sound FX: another click, a foghorn]
[0.5seconds]
[Spoken, laughing at himself]
"That was also not the jingle."
[0.5seconds]
"Third time lucky."
[Outro: the correct beat finally kicks in]
```

## 79 — The Intern

- Style Suno : `radio imaging, keen young voice, studio ambience, bright beat, 14s`
- Durée cible : 14 s

```
[Sound FX: studio ambience, a chair rolling]
[0.5seconds]
[Spoken, keen young voice, slightly too close to the mic]
"Am I doing it right? Am I too close?"
[Sound FX: gentle laughter off-mic]
[0.5seconds]
[Spoken, warm voice from further away]
"You are perfect. Say the thing."
[0.5seconds]
[Spoken, keen voice, beaming]
"Free music, no adverts!"
[Outro: bright beat kicks in]
```

## 80 — Signing On

- Style Suno : `radio imaging, bright happy morning voice, carrier tone, uplifting house, 15s`
- Durée cible : 15 s

```
[Sound FX: a switch, a carrier tone waking up, early gulls]
[0.5seconds]
[Spoken, bright and genuinely happy to be there]
"Good morning. The kettle is on and the sun is coming up."
[Sound FX: a warm chord fades in with the light]
[0.5seconds]
[Spoken, smiling]
"Same as yesterday. Same as tomorrow."
[0.5seconds]
"Glad you are here."
[Outro: chord resolves into the first beat of the day]
```

---

## Ordre de production conseillé

1. **Le tag d'abord** — 3 ou 4 prises, garder la meilleure. Rien d'autre ne peut être
   finalisé avant.
2. **Le n° 01 ensuite**, puis coller le tag et écouter. C'est le seul test qui valide la
   règle 2 (résolution nette plutôt que fondu). Si le raccord sonne collé, corriger les
   outros des 49 autres avant de lancer la production.
3. **Le reste par famille**, pour garder une cohérence de voix et de lit musical à
   l'intérieur de chaque bloc.
4. Normaliser les 50 fichiers finis en `loudnorm` (voir la commande plus haut) avant
   l'upload SFTP, puis les rattacher un par un à la playlist Jingles — l'appartenance à une
   playlist AzuraCast est un **champ par fichier**, pas une règle de dossier. C'est
   exactement le piège qui avait laissé la playlist Kalbass vide malgré 13 fichiers uploadés.
