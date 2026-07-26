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
olarak kişileştiriliyor — bir robot değil, sevimli bir karakter değil,
ışıktan ve sözdiziminden yapılmış güçlü, elementer bir güç. Üç banner,
README boyunca anlatılan TEK bir hikayenin üç sahnesi:

1. **Kovalamaca** — kaçışan, dağılan kod parçaları (soluk, pas-amber,
   ürkmüş kıvılcımlar gibi kocaman karanlık bir dijital boşlukta
   savruluyor) bekçinin uzanan eliyle yakalanıyor — hiçbiri kaçamıyor.
   (Bu, hibrit aramanın kendisi: hiçbir şey ondan saklanamaz.)
2. **İçerideki Dökümhane** — bekçinin kendi ışıldayan göğüs-çekirdeğinin
   içinde, yakalanan parçalar tutuluyor, çapraz referanslanıyor,
   karşılaştırılıyor, notlandırılıyor — yalnız saklanmıyor, üzerinde
   çalışılıyor. (Bu, derin araştırma, karşılaştırma tablosu, sembol
   grafiği, manual üreticinin kendisi.)
3. **Serbest Bırakma** — bekçi elini açıp aynı parçaları geri gönderiyor,
   ama artık dönüşmüş halde: küçük ve dağınık değil, büyük, som,
   parlak, eksiksiz. (Bu, geliştiriciye geri dönen zenginleştirilmiş
   cevap, açıklama veya dokümantasyonun kendisi.)

- **Dünya:** kocaman, karanlık bir dijital boşluk (bir ekran değil, uzay
  da değil — sınırsız kod tabanı ölçeğini ima eden dipsiz karanlık bir
  genişlik). Bekçinin bedeni, çekirdekte yoğun, uçlara doğru ince
  ışıklı ipliklere ayrılan, akan, ışıldayan sözdizimi-benzeri devre
  şeritlerinden inşa edilmiş — güçlü ve elementer, sevimli-maskot değil.
- **Palet:** neredeyse-siyah boşluk (temel), parlak elektrik
  camgöbeği-beyaz (bekçi, ve dokunup dönüştürdüğü her şey), soluk
  pas-amber (kaçan/işlenmemiş, yakalanmadan önceki kod) — camgöbeği-
  amber karşıtlığının kendisi tüm hikayenin öncesi/sonrası.
- **Stil:** epik sinematik dijital resim, dramatik kenar aydınlatması
  (rim lighting), güçlü ölçek ve hareket hissi, parçacık/ışık-izi
  detayı.
- **Tutarlılık:** üç görsel de bu tam bekçiyi, dünyayı ve paleti
  paylaşır; her biri aynı hikayenin farklı bir sahnesi, farklı bir
  çekim türü ve kamera açısıyla.

## Negatif Prompt (her üretimde yapıştırın)

```
text, letters, readable words, logos, watermark, low quality, blurry,
cute, chibi, cartoon mascot, toy-like, humans, real robots, screens,
monitors, keyboards, office setting, different art style between images
```

## Görsel 1 — Genel Bakış / Kovalamaca (`docs/images/overview.png`)

**Konum:** README'nin en üstü, başlık/rozetlerin altında.
**Çekim:** geniş dinamik aksiyon çekimi, çapraz kompozisyon, kaçan
parçalarda güçlü hareket bulanıklığı — tüm dünyayı ve hikayeyi kurar.

**Prompt (İngilizce, aynen kullanın):**
```
Epic cinematic digital painting. In a vast, bottomless dark digital
void, a swarm of small, dim, rust-amber code-fragments — jagged
splinters of glowing syntax, like startled sparks — are scrambling and
scattering in every direction as if trying to flee. From the edge of
frame, an enormous, powerful Guardian made entirely of flowing,
brilliant electric cyan-white circuitry and living code-ribbons reaches
in with one massive glowing hand, closing its grip around a cluster of
the fleeing fragments mid-flight. The fragments already caught in its
hand are transforming, glowing brighter, shifting from dim rust-amber to
brilliant cyan. Many more fragments still scatter and flee in the
distance, but none of them will get away. Strong diagonal composition,
dramatic motion blur on the fleeing fragments, powerful rim lighting on
the Guardian's hand and arm, near-black void background, particle and
light-trail detail. No text, no readable words, not cute or cartoonish —
epic and powerful. Wide 16:9 banner composition, highly detailed.
```

## Görsel 2 — Temel Yetenekler / İçerideki Dökümhane (`docs/images/core-features.png`)

**Konum:** "Temel Yetenekler" bölümünün en üstü.
**Çekim:** orta çekim, kamera bekçinin yarı saydam göğüs-çekirdeğinin
içine itilmiş, yakalanan parçaların üzerinde çalışılışına bakıyor —
Görsel 1'den daha yakın ve samimi, tamamen farklı bir açı.

**Prompt (İngilizce, aynen kullanın):**
```
Epic cinematic digital painting. Inside the luminous, translucent
chest-core of a towering Guardian made of brilliant electric cyan-white
circuitry, four captured code-fragments — now glowing solid cyan, no
longer dim amber — are suspended and actively being worked on, each in a
clearly distinct way so they read as four separate ideas: (1) one
fragment with fine threads of light branching outward from it to three
smaller sibling fragments, like a nervous system — cross-referencing
relationships; (2) two nearly-identical fragments held side by side,
one glowing subtly brighter than the other as if being judged and
scored — comparison and evaluation; (3) one fragment wrapped in a second,
outer layer of finer annotation-light, like a manuscript gaining
margin notes — documentation being generated around it; (4) one
fragment held against a faint mirror-echo of itself, with only the
genuinely matching parts lighting up — verification, not assumption.
All of this suspended inside a vast glowing chamber of circuitry, near-
black void just visible beyond the translucent chest wall, powerful rim
lighting, particle and light-trail detail. No text, no readable words,
not cute or cartoonish — epic and powerful. Wide 16:9 banner
composition, highly detailed.
```

## Görsel 3 — Tasarım ve Felsefe / Serbest Bırakma (`docs/images/design-philosophy.png`)

**Konum:** "Tasarım ve Felsefe" bölümünün en üstü.
**Çekim:** dramatik alçak açılı yakın çekim — üçünün en sıra dışı
çerçevelemesi — bekçinin çalışmasını dünyaya geri salarken açılan
elinin altından yukarı bakan bir kamera.

**Prompt (İngilizce, aynen kullanın):**
```
Epic cinematic digital painting, dramatic low-angle shot looking up
from below. A towering Guardian made of brilliant electric cyan-white
circuitry opens its massive glowing hand, releasing several
code-fragments back out into the vast dark void — but these fragments
are no longer the small, dim, scattered sparks they were before capture;
they are now large, solid, brilliant crystalline constructs of pure
cyan light, complex and complete, flying outward powerfully with bright
trailing light-streaks, dwarfing what they used to be. The Guardian's
open hand and forearm fill the lower foreground in dramatic
silhouette-lit close-up, the released constructs soaring up and away
into the dark distance above. Near-black void, powerful rim lighting,
strong sense of scale and motion, particle and light-trail detail. No
text, no readable words, not cute or cartoonish — epic and powerful.
Wide 16:9 banner composition, highly detailed.
```
