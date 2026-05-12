# LinkTube Downloader

App web serverless para Vercel que recebe um link de vídeo e tenta gerar um link direto de download usando `yt-dlp`.

## Deploy na Vercel

Se o projeto local ainda não estiver vinculado na Vercel, rode uma vez:

```bash
vercel link --yes --project downloaderytvideos
```

Valide o build local da Vercel:

```bash
vercel build --yes
```

Publique em produção:

```bash
vercel --prod
```

Para um deploy de preview, use:

```bash
vercel
```

## Arquitetura

- `index.html`, `styles.css` e `app.js`: frontend estático.
- `api/download.py`: Function serverless que resolve o link direto.
- `api/downloads.py`: endpoint informativo, porque a Vercel serverless não mantém uma biblioteca local persistente.
- `requirements.txt`: instala `yt-dlp` no deploy.

## Importante

Serverless na Vercel tem limite de tempo e não é ideal para baixar, converter e armazenar vídeos grandes. Esta versão retorna um link direto temporário para o navegador baixar.

Alguns vídeos do YouTube podem exigir sessão/cookies quando a requisição vem de servidores cloud como a Vercel. Para esses casos, configure uma variável de ambiente chamada `YOUTUBE_COOKIES_BASE64` com seus cookies exportados em formato Netscape e codificados em base64:

```bash
base64 -w 0 cookies.txt
```

Depois adicione o valor no painel da Vercel em Project Settings > Environment Variables, ou pela CLI:

```bash
vercel env add YOUTUBE_COOKIES_BASE64 production
```

Nunca faça commit do arquivo `cookies.txt`.

Para um downloader mais parecido com aTube, use a Vercel só para o site e conecte um worker externo com armazenamento, como Railway/Render/Fly.io + S3/R2/Supabase Storage.

## Desenvolvimento local

Instale a Vercel CLI e rode:

```bash
vercel dev
```

Use apenas links de vídeos que você tem direito de baixar.
