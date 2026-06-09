# Principia Local Setup Instructions

This folder is a clean, blank-data copy of Principia. Follow these steps on your own computer.

## 1. Open A Terminal

Go to the folder:

```bash
cd /path/to/Principia-demo-jun9-ready
```

For example, if the folder is on your Desktop:

```bash
cd ~/Desktop/Principia-demo-jun9-ready
```

## 2. Start The Local App

```bash
python3 principia.py serve
```

Keep this terminal window open while using the app.

## 3. Open The Browser

Open:

```text
http://127.0.0.1:8790/
```

## 4. Add Your API Key

In the app, click:

```text
API Keys
```

Enter your own SiliconFlow key, OpenAI key, or both. The app writes them into a local `.env` file in this folder.

You can also create `.env` manually:

```bash
cp .env.example .env
```

Then edit `.env`.

## 5. Use The Workflow

1. Create a project.
2. Enter a research goal or idea draft.
3. Choose an LLM and target work count.
4. Click `Research`.
5. Review Existed Ideas, Benchmarks, Baselines, Principles, and Takeaway Messages.
6. Click `Generate Idea`.
7. Select evidence, add your own idea note, choose an LLM, and generate a new idea.
8. Open the generated idea details from `My Ideas`.

## 6. Important Behavior

- Principia stores data locally in `data/principia.sqlite`.
- This package starts with no database.
- If the LLM cannot be called, Principia should show an alert instead of using template-like generated content.
- OpenAI API access is separate from a ChatGPT Plus/Pro subscription. If OpenAI API calls fail, check API billing, project permissions, model access, and the key copied into `.env`.

## 7. Troubleshooting

### Port Already In Use

Use another port:

```bash
python3 principia.py serve --host 127.0.0.1 --port 8791
```

Then open:

```text
http://127.0.0.1:8791/
```

### SSL Certificate Error

First try updating Python certificates. For a local demo only, you may set this in `.env`:

```text
PRINCIPIA_SSL_VERIFY=0
```

### LLM Timeout

Increase the timeout in `.env`:

```text
PRINCIPIA_REQUEST_TIMEOUT=240
```

You can also reduce `Target Works` in the UI to make research runs shorter.

### Reset All Local Data

```bash
python3 principia.py reset --yes
```

## 8. Optional Test

Install optional test dependency:

```bash
python3 -m pip install -r requirements.txt
```

Run:

```bash
python3 -m unittest discover -s tests -p 'test*.py'
```
