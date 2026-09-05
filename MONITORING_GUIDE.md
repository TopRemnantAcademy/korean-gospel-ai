# =========================================================
# - Monitoring Setup Guide
# =========================================================
# This guide explains how to setup monitoring with Langfuse
# =========================================================

## 📊 Why Monitor?

- **Trace every LLM call** (input, output, latency)
- **Debug issues** (what was the input? why did it respond that way?)
- **Monitor costs** (token usage per provider)
- **Setup alerts** (errors, slow responses)
- **User feedback** (thumbs up/down)

---

## 🔍 Langfuse Setup

### Step 1: Create Langfuse account

1. Go to https://cloud.langfuse.com
2. Sign up (free tier: 50K traces/month)
3. Create a new project: "korean-gospel-ai"

### Step 2: Get API keys

1. Go to **Settings → API Keys**
2. Copy **Public Key** (starts with `pk-lf-...`)
3. Copy **Secret Key** (starts with `sk-lf-...`)

### Step 3: Configure backend

Edit `.env.production`:

```bash
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
```

### Step 4: Redeploy

```bash
./deploy.sh production
```

---

## 📈 What to Monitor

### 1. **LLM Performance**

- **Latency**: Target <3s for non-streaming, <500ms first token for streaming
- **Token usage**: Monitor per provider (Gemini vs DeepSeek)
- **Error rate**: Should be <1%

**Langfuse query**:
```
event_type: "LLM" AND level: "ERROR"
```

### 2. **Retrieval Quality**

- **Chunk relevance**: Are retrieved chunks relevant?
- **No results**: How often does retrieval return 0 results?
- **Low score**: Chunks with score <0.5

**Check traces**:
- Look for traces with `retrieval.count == 0`
- Check `retrieval.score` distribution

### 3. **User Feedback**

- **Thumbs up/down**: Track in Interaction table
- **Corrections**: When users correct the answer
- **Repeat questions**: User didn't get good answer first time

**Langfuse query**:
```
observation_type: "feedback"
```

### 4. **System Health**

- **/health endpoint**: Should return 200 always
- **Qdrant health**: Check collection stats
- **Database**: SQLite file size, query performance

**Setup uptime monitoring** (external):
- UptimeRobot: https://uptimerobot.com
- PingPromise: https://pingPromise.com

---

## 🚨 Alerts Setup

### Langfuse Alerts

1. Go to **Langfuse Dashboard → Alerts**
2. Create alerts for:

#### Alert 1: High Error Rate
```
Condition: error_rate > 5% over 10 minutes
Channel: Email + Slack
```

#### Alert 2: Slow Responses
```
Condition: p95_latency > 10s over 5 minutes
Channel: Email
```

#### Alert 3: High Token Usage
```
Condition: daily_tokens > 100,000
Channel: Email
```

### Slack Integration

1. In Langfuse: **Settings → Integrations → Slack**
2. Connect Slack workspace
3. Choose channel: `#korean-gospel-alerts`

---

## 📊 Qdrant Monitoring

### Check collection stats

```bash
curl -H "api-key: <your-key>" \
  https://your-cluster.qdrant.tech:6333/collections/gospel_kure
```

**Monitor**:
- `points_count`: Should grow as you add documents
- `segments_count`: Memory usage indicator
- `status`: Should be "green"

### Setup Qdrant Cloud alerts

1. Go to [Qdrant Cloud Dashboard](https://cloud.qdrant.tech)
2. **Monitoring → Alerts**
3. Set alerts for:
   - High memory usage (>80%)
   - High CPU usage (>80%)
   - Slow queries (>1s)

---

## 📝 Custom Logging

### Add custom events to code

```python
from langfuse.decorators import observe, langfuse_context

# Trace a custom event
@observe()
def my_function():
    langfuse_context.update_current_observation(
        metadata={"custom_field": "value"}
    )
    # ... your code ...
```

### Log business metrics

```python
# In interaction save
if trace:
    trace.event(name="user_feedback", output={
        "interaction_id": interaction.id,
        "feedback": feedback, # 👍 or 👎
        "comment": comment,
    })
```

---

## 📈 Dashboards

### Create Langfuse Dashboard

1. Go to **Langfuse → Dashboards**
2. Create dashboard: " - Production"
3. Add widgets:

#### Widget 1: Daily Token Usage
```
Metric: total_tokens
Group by: day
Chart: Bar chart
```

#### Widget 2: LLM Provider Distribution
```
Metric: count
Group by: llm_provider
Chart: Pie chart
```

#### Widget 3: Error Rate Over Time
```
Metric: error_rate
Group by: hour
Chart: Line chart
```

#### Widget 4: Top User Questions
```
Event: "input_policy"
Group by: input
Metric: count
Chart: Table
```

---

## 🔍 Debugging with Langfuse

### Example 1: Why did the model respond wrongly?

1. Go to **Langfuse → Traces**
2. Filter by `trace_id` (from Interaction table)
3. Check:
   - **Input**: Was the question clear?
   - **Retrieval**: Did it retrieve relevant chunks?
   - **Prompt**: Was the system prompt correct?
   - **Output**: What did the model generate?

### Example 2: Why is latency high?

1. Go to **Langfuse → Observations**
2. Filter by `trace_id`
3. Check timing:
   - `retrieval` duration: Should be <500ms
   - `LLM` duration: Should be <3s (non-streaming)
   - `generation` duration: Time to first token (streaming)

### Example 3: Why was a chunk blocked?

1. Go to **Langfuse → Traces**
2. Filter by `trace_id`
3. Check `quality_gate` event:
   - `blocked`: true/false
   - `errors`: Why was it blocked?
   - `warnings`: What were the warnings?

---

## 📊 Cost Tracking

### Langfuse Cost Dashboard

1. Go to **Langfuse → Cost**
2. View:
   - **Total cost per day**
   - **Cost per provider** (Gemini vs DeepSeek)
   - **Cost per user** (if using token quotas)

### Estimate costs

**Gemini 2.5 Flash**:
- Input: $0.075 / 1M tokens
- Output: $0.30 / 1M tokens
- *Example*: 1000 questions/day × 500 tokens = ~$0.04/day

**DeepSeek V4 Flash**:
- Input: $0.014 / 1M tokens
- Output: $0.028 / 1M tokens
- *Example*: 1000 questions/day × 500 tokens = ~$0.008/day

**Total estimated cost** (1000 questions/day):
- Gemini: ~$12/month
- DeepSeek: ~$2.50/month

---

## 🔒 Security Monitoring

### Monitor for abuse

**Langfuse query**:
```
input_policy.allowed: false
```

**Check for**:
- Rate limit violations
- Token quota exceeded
- Blocked inputs (policy violations)

### Setup alert

```
Condition: input_policy.allowed == false > 10 times in 1 hour
Action: Send alert to admin
```

---

## 📋 Monthly Review Checklist

- [ ] Review Langfuse dashboard (token usage, costs, errors)
- [ ] Check Qdrant collection stats (points count, memory usage)
- [ ] Review user feedback (thumbs up/down ratio)
- [ ] Check for repeated questions (retrieval quality issue?)
- [ ] Review slow traces (optimization opportunity)
- [ ] Check error logs (fix bugs)
- [ ] Review security alerts (blocked inputs)
- [ ] Estimate next month's costs

---

## 🆘 Troubleshooting

### Langfuse not receiving traces

**Check**:
1. `LANGFUSE_ENABLED=true` in `.env`
2. `LANGFUSE_PUBLIC_KEY` starts with `pk-lf-`
3. `LANGFUSE_SECRET_KEY` starts with `sk-lf-`
4. Backend can reach `LANGFUSE_HOST` (no firewall blocking)

**Debug**:
```bash
# Check backend logs for Langfuse errors
grep -i "langfuse" logs/backend.log
```

### Traces are delayed

- Langfuse batches traces (sends every 10s)
- Wait 10-30s after request to see in dashboard

### Missing metadata

- Ensure `@observe()` decorator is on the function
- Check `langfuse_context.update_current_observation()` is called

---

## 📞 Support

- **Langfuse Docs**: https://langfuse.com/docs
- **Langfuse Community**: https://github.com/langfuse/langfuse/discussions
- **Qdrant Docs**: https://qdrant.tech/documentation/
