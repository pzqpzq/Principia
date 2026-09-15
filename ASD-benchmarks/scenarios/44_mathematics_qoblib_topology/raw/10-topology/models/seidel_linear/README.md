# Linearized Seidel-APSP Model

This directory contains the linearized Seidel All-Pairs Shortest Path formulation for the Network Topology Design problem.

The Linearized Model reformulates the quadratic terms from the [Quadratic Model](./../seidel_quadratic/) into linear constraints.

## Linearization Technique

To linearize the quadratic terms in the Seidel-APSP Model, we introduce a binary variable $y_{stuj}$, where:

$$
y_{stuj} \coloneqq \text{dist}_{suj} \cdot \text{dist}_{ut1}
$$

This variable is $1$ if both $\text{dist}_{suj}$ and $\text{dist}_{ut1}$ are $1$, and $0$ otherwise. Using this variable, the quadratic terms are replaced with the following linear constraints:

$$
\begin{align}
    y_{stuj} &\leq \text{dist}_{suj} \\
    y_{stuj} &\leq \text{dist}_{ut1} \\
    y_{stuj} &\geq \text{dist}_{suj} + \text{dist}_{ut1} - 1
\end{align}
$$

## Model Constraints

**Distance calculation:**

$$
\begin{align*}
    \forall s, t \in V, s \neq t, \forall j \in \{1, \dots, n-1\}: \quad
    \text{dist}_{st(j+1)} &\leq \text{dist}_{stj} + \sum_{u \in V, u \neq s, u \neq t} y_{stuj}
\end{align*}
$$

**Linearization constraints:**

$$
\begin{align*}
    \text{Linearization 1:} \quad & \forall s, t \in V, s \neq t, \forall j \in \{1, \dots, n-1\}, \forall u \in V \setminus \{s, t\}: \\
    & y_{stuj} \leq \text{dist}_{suj} \\
    \text{Linearization 2:} \quad & \forall s, t \in V, s \neq t, \forall j \in \{1, \dots, n-1\}, \forall u \in V \setminus \{s, t\}: \\
    & y_{stuj} \leq \text{dist}_{ut1}
\end{align*}
$$

**Variable domains:**

$$
y_{stuj} \in \{0, 1\}, \quad \forall s, t \in V, s \neq t, \forall j \in \{1, \dots, n-1\}, \forall u \in V \setminus \{s, t\}
$$
