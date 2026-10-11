# Feya 2.0 — Read this first

**Date:** 11 October 2026  
**Status:** Design proposal + competitor desk research; **nothing here proves Feya has a competitive advantage yet**.

## Decision in one sentence

Build an **open-source business agent suite** that carries out routine work autonomously, tracks tasks and cases, and asks humans to approve critical actions such as sending emails or invoices. An independent gateway enforces permissions and approved actions and verifies provider results.

## Files

1. [`01_COMPETITIVE_LANDSCAPE.md`](01_COMPETITIVE_LANDSCAPE.md) — Hermes Kanban, OpenClaw, n8n, Activepieces, Dify, LangGraph, CrewAI, agent frameworks, strategic options and a fair comparison benchmark.
2. [`02_PRODUCT_TECHNICAL_SPEC.md`](02_PRODUCT_TECHNICAL_SPEC.md) — product requirements, design principles, UX, technical stack, trust boundaries, data contracts, state model, API, reliability, security, tests, migration, OSS release checklist, architecture decisions, and concrete starter tickets.

## Reality check

Today's [Feya repository](https://github.com/selectqoma/feya) includes a live company-specific Claude Code deployment, a Hermes scaffold, Telegram and console reliability work, and a CRM pilot. It is **not already** the proposed platform. The public repo currently has no root license visible in source review; public source does not by itself grant OSI open-source rights. Tracked company-specific/deployment material and repository history need review before public OSS packaging.

Also, **Hermes now has durable Kanban with human review, retries and multi-profile agents**. The claim “Feya has workflows/approval, Hermes does not” is false. Feya’s product focus is autonomous business work with persistent tasks and cases, evidence, approval for critical actions and verified outcomes.

## The first ten tickets

FEA-001 clean new repo and CI; FEA-002 domain models; FEA-003 cases/events/outbox; FEA-004 fake provider; FEA-005 durable workflow; FEA-006 hard policy gateway; FEA-007 structured agent runner; FEA-008 draft and verification; FEA-009 case UI; FEA-010 Hermes/n8n comparative spike. See §22 of the spec for the concrete descriptions.

## The first demo to build

A synthetic customer sends an incomplete enquiry. Feya creates one durable case, points to source evidence, identifies missing facts, and prepares a draft. After an external reply, it builds a price-validated proposed offer, passes through policy to a fake provider and verifies the exact result. Duplicate events, forged approvals and lost provider responses are handled without inventing success or creating duplicate offers.

## Non-negotiable publication gates

- Clean-room source, approved license, secret/PII/history review and contributor rights.
- No unauthorized writes or duplicate high-impact operations in security/fault suite.
- Separate second business pack working without editing core.
- Reproducible head-to-head comparison with Hermes Kanban and at least one workflow automation platform.
- Clear self-hosted install, complete tested quickstart and actionable operator UI.

**Suggested starting move:** run a short technical spike comparing **Hermes Kanban + Feya case/policy extension** with **independent `Case/Action/Gateway` Python vertical slice**, using exactly the same synthetic enquiry and fault tests. Preserve the decision in an architecture record before committing to the full engine.
