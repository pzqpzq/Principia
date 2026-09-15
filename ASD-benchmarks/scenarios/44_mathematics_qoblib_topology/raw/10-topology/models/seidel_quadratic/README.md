# Quadratic Seidel-APSP Model

This directory contains the quadratically-constrained Seidel All-Pairs Shortest Path formulation for the Network Topology Design problem.

This formulation uses a set of binary variables to represent the shortest path lengths, while the rest of the formulation remains the same as in the [multicommodity flow formulation](./../flow_mip/). This formulation is called Seidel due to the fact that it uses Seidel's model for all-pair shortest paths.

The quadratic constraints only involve binary variables and can be linearized, leading to the [linearized formulation](./../seidel_linear/).

## Model

$$
\begin{align*}
    \min \; & k \\
    \text{s.t.: (diameter) } & \forall s,t \in V, s\neq t:\quad p_{st} \le k \\
    \text{(SP summation)} \quad & \forall s, t \in V, s \neq t:\quad p_{st} = 1 + \sum_{j=1}^{n} \big(1 - \text{dist}_{stj}\big), \\
    \text{(Distance calculation)} \quad & \forall j \in \{1, \dots, n-1\}, \forall s, t \in V : \\
    & \text{dist}_{st(j+1)} \leq \text{dist}_{stj} + \sum_{u \in V, u \neq s, u \neq t} \text{dist}_{suj} \cdot \text{dist}_{ut1},
\end{align*}
$$
$$
\begin{align*}
    \text{(Distance constraints)} \quad & \forall u \in V \setminus \{s, t\}:\quad \text{dist}_{st(j+1)} \geq \text{dist}_{suj} \cdot \text{dist}_{ut1}, \\
    & \text{dist}_{st(j+1)} \geq \text{dist}_{stj}, \\
    \text{(Node degree constraint)} \quad & \forall i \in V:\quad \sum_{j \in V, j \neq i} \text{dist}_{ij1} \leq d, \\
    \text{(Variable domains)} \quad & \forall s, t \in V, s \neq t:\quad p_{st} \in \mathbb{N}, \forall s, t \in V, s \neq t, \forall j \in \{1, \dots, n\} : \text{dist}_{stj} \in \{0, 1\}.
\end{align*}
$$

## Description

The model uses an auxiliary variable $\text{dist}_{stj}$ to track whether a path of length $j$ or shorter exists between nodes $s$ and $t$. It starts with the adjacency matrix of the graph, which represents the graph by indicating whether a direct edge exists between any two nodes. Then it iteratively squares the adjacency matrix to check whether paths of increasing lengths through intermediate nodes exist between pairs of nodes. 
