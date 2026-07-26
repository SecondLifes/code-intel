# AI Görsel Prompt'ları — README Banner'ları

Bu kitin `README.md` / `README.tr-TR.md`'si için üç banner görseli.
Herhangi bir yetenekli görsel modeliyle (Nano Banana Pro, Midjourney v7,
Flux, GPT-Image, vb.) **geniş 16:9 banner en-boy oranında** üretin,
`docs/images/` altına PNG olarak kaydedin (`overview.png`,
`core-features.png`, `design-philosophy.png` — büyük model çıktısını
önce `tools/resize-images.bat` ile küçültün). `README.md`/`README.tr-TR.md`
görsel etiketleri **açık** taşınır — dosyalar iner inmez görseller belirir.

Bu dosya **kendi kendine yeterli** — devralınacak ortak bir temel prompt
yok. Bu kit tamamen kendine özgü bir görsel dünyaya sahip.

## Sanat yönü — "Kodun Bekçisi" (The Guardian of Code) — statik bir maskot değil, 3 perdelik bir hikaye

CodeIntel, tüm bedeni canlı, ışıldayan koddan örülmüş devasa bir bekçi
olarak kişileştiriliyor — bir robot değil, sevimli bir karakter değil.
Onu tanımlayan şey bir **ikilik**: aradığı hiçbir şeyin asla kaybolmadığı,
muazzam ve tartışmasız bir güç ve kesinlik — ama bunun yanında tam bir
yumuşaklık, masumiyet ve şefkat. Asla avlamıyor ya da kapmıyor;
*topluyor* — fırtına öncesi dağılmış kuzuları toplayan bir çoban gibi,
ya da ürkmüş bir çocuğu kucaklayan bir ebeveyn gibi: kesin ve emin
elli, ama yumuşak, koruyucu, en ufak bir tehdit izi taşımadan. Üç
banner, README boyunca anlatılan TEK bir hikayenin üç sahnesi:

1. **Toplama** — küçük, dağılmış kod parçaları (soluk, pas-amber,
   sürüsünden ayrılmış ateşböcekleri gibi kocaman karanlık bir dijital
   boşlukta savrulan ve kaybolmuş, korkudan kaçan değil) bekçinin açık,
   nazik elleri tarafından kucaklanıp içeri çekiliyor — hiçbiri kayıp
   kalmıyor, ama hiçbiri de kabaca kapılmıyor. (Bu, hibrit aramanın
   kendisi: kesin, ama özenli.)
2. **İçerideki Şefkat** — bekçinin kendi ışıldayan göğüs-çekirdeğinin
   içinde, toplanan parçalar kucaklanıyor, çapraz referanslanıyor,
   karşılaştırılıyor, notlandırılıyor — bir öğretmenin öğrettiği gibi
   ilgileniliyor, bir makinenin işlediği gibi değil. (Bu, derin
   araştırma, karşılaştırma tablosu, sembol grafiği, manual üreticinin
   kendisi.)
3. **Serbest Bırakma** — bekçi sessiz bir gururla ellerini açıp aynı
   parçaları geri gönderiyor, ama artık dönüşmüş halde: küçük ve kayıp
   değil, büyük, som, parlak, eksiksiz — büyümüş bir çocuğunu evden
   uğurlayan bir ebeveyn gibi. (Bu, geliştiriciye geri dönen
   zenginleştirilmiş cevap, açıklama veya dokümantasyonun kendisi.)

- **Dünya:** kocaman, karanlık bir dijital boşluk (bir ekran değil, uzay
  da değil — sınırsız kod tabanı ölçeğini ima eden dipsiz karanlık bir
  genişlik). Bekçinin bedeni, çekirdekte yoğun ve sıcak, uçlara doğru
  ince ışıklı ipliklere yumuşayan, akan, ışıldayan sözdizimi-benzeri
  devre şeritlerinden inşa edilmiş — ölçekte güçlü, her jest ve duruşta
  yumuşak; duruşunda hiçbir şey asla tehditkâr okunmuyor.
- **Palet:** neredeyse-siyah boşluk (temel), sıcak, yumuşak bir iç
  parıltıya sahip parlak elektrik camgöbeği-beyaz — asla sert veya soğuk
  değil — (bekçi, ve dokunup dönüştürdüğü her şey), soluk pas-amber
  (toplanmadan önceki kayıp/işlenmemiş kod) — camgöbeği-amber
  karşıtlığının kendisi tüm hikayenin öncesi/sonrası, ve bekçinin ışığı
  her zaman kör edici değil şefkatli hissettirmeli.
- **Stil:** sinematik dijital resim, sert kenar aydınlatması yerine
  yumuşak hacimsel parıltı, epik ölçekte bile şefkatli ve saygılı bir
  ruh hali, parçacık/ışık-izi detayı.
- **Tutarlılık:** üç görsel de bu tam bekçiyi, dünyayı ve paleti
  paylaşır; her biri aynı hikayenin farklı bir sahnesi, farklı bir
  çekim türü ve kamera açısıyla.

## Negatif Prompt (her üretimde yapıştırın)

```
text, letters, readable words, logos, watermark, low quality, blurry,
menacing, aggressive, predatory, monstrous, cute, chibi, cartoon mascot,
toy-like, humans, real robots, screens, monitors, keyboards, office
setting, different art style between images
```

## Görsel 1 — Genel Bakış / Toplama (`docs/images/overview.png`)

**Konum:** README'nin en üstü, başlık/rozetlerin altında.
**Çekim:** geniş dinamik çekim, çapraz kompozisyon, savrulan parçalarda
yumuşak bir hareket — tüm dünyayı ve hikayeyi kurar.

**Prompt (İngilizce, aynen kullanın):**
```
Cinematic digital painting. In a vast, bottomless dark digital void, a
scatter of small, dim, rust-amber code-fragments — soft jagged splinters
of glowing syntax, like fireflies lost from their swarm — drift and
wander in every direction, disoriented rather than fleeing in fear.
From the edge of frame, an enormous Guardian made entirely of flowing,
brilliant electric cyan-white circuitry and living code-ribbons reaches
in with both open hands, cupped gently rather than grasping, drawing a
cluster of the lost fragments toward its palms with unmistakable
certainty but total tenderness. The fragments already gathered are
softening into a warmer glow, shifting from dim rust-amber toward
brilliant cyan as they near the Guardian's hands. Many more fragments
still drift in the distance, but not one of them will be left behind.
Strong diagonal composition, gentle motion blur on the drifting
fragments, soft warm volumetric glow around the Guardian's hands and
arms — powerful in scale, protective and unthreatening in posture —
near-black void background, particle and light-trail detail. No text,
no readable words, not menacing, not cute or cartoonish — immense yet
tender. Wide 16:9 banner composition, highly detailed.
```

## Görsel 2 — Temel Yetenekler / İçerideki Şefkat (`docs/images/core-features.png`)

**Konum:** "Temel Yetenekler" bölümünün en üstü.
**Çekim:** orta çekim, kamera bekçinin yarı saydam göğüs-çekirdeğinin
içine itilmiş, toplanan parçaların üzerinde nasıl özenle ilgilenildiğine
bakıyor — Görsel 1'den daha yakın ve samimi, tamamen farklı bir açı.

**Prompt (İngilizce, aynen kullanın):**
```
Cinematic digital painting. Inside the luminous, translucent chest-core
of a towering Guardian made of brilliant electric cyan-white circuitry,
four gathered code-fragments — now glowing a warm solid cyan, no longer
dim amber — rest cradled in soft light, each being tended to in a
clearly distinct way so they read as four separate ideas, all rendered
gently rather than clinically: (1) one fragment with fine threads of
light branching outward from it to three smaller sibling fragments, like
a hand resting on each in turn — cross-referencing relationships; (2)
two nearly-identical fragments held close together side by side, one
glowing subtly brighter as if being lovingly, carefully compared, not
judged; (3) one fragment wrapped in a second, soft outer layer of finer
annotation-light, like a blanket of margin notes — documentation being
generated around it; (4) one fragment held gently against a faint
mirror-echo of itself, only the genuinely matching parts warming into
light — patient verification, not assumption. All of this cradled inside
a vast, warmly glowing chamber of circuitry, near-black void just
visible beyond the translucent chest wall, soft volumetric glow rather
than harsh light, particle and light-trail detail. No text, no readable
words, not menacing, not cute or cartoonish — immense yet tender. Wide
16:9 banner composition, highly detailed.
```

## Görsel 3 — Tasarım ve Felsefe / Serbest Bırakma (`docs/images/design-philosophy.png`)

**Konum:** "Tasarım ve Felsefe" bölümünün en üstü.
**Çekim:** dramatik alçak açılı yakın çekim — üçünün en sıra dışı
çerçevelemesi — bekçinin çalışmasını dünyaya geri salarken açılan
ellerinin altından yukarı bakan bir kamera.

**Prompt (İngilizce, aynen kullanın):**
```
Cinematic digital painting, low-angle shot looking up from below. A
towering Guardian made of brilliant electric cyan-white circuitry opens
its hands slowly and with quiet pride, releasing several code-fragments
back out into the vast dark void — not thrown or launched, but let go
gently, the way a parent lets a grown child step forward on their own.
These fragments are no longer the small, dim, lost sparks they were
before gathering; they are now large, solid, brilliant crystalline
constructs of warm cyan light, complex and complete, drifting outward
steadily and confidently with soft trailing light-streaks, dwarfing what
they used to be. The Guardian's open hands and forearms fill the lower
foreground in a tender, reverent close-up, softly rim-lit rather than
harshly silhouetted, the released constructs rising up and away into the
dark distance above like something being sent off with love. Near-black
void, soft warm volumetric glow, strong sense of scale without menace,
particle and light-trail detail. No text, no readable words, not
menacing, not cute or cartoonish — immense yet tender. Wide 16:9 banner
composition, highly detailed.
```
