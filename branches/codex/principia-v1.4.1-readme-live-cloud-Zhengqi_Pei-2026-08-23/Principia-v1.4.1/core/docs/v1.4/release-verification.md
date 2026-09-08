# Release verification

Builds are intentionally publication-neutral:

```bash
python -m build
python -m pip install dist/principia_ai-1.4.0-py3-none-any.whl
principia doctor --json
```

Verify the wheel and sdist SHA-256 values against the signed handoff receipt. The wheel must include `principia/openapi-v1.json`, the five JSON Schemas, `principia/ui_dist/index.html`, compiled UI assets, and no source maps.

The private acceptance repository supplies fail-closed gates for backend, contract, bounded live LLM, frontend/browser/accessibility, scale performance, clean artifacts, and a reproducible installed-wheel demo. It uses only labelled synthetic area packages and public synthetic prompts. No workflow in the v1.4.0 implementation run publishes to GitHub, PyPI, TestPyPI, or a real Global Cloud.
