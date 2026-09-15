# Multi-Commodity Flow Model

This directory contains the multi-commodity flow formulation for the Network Topology Design problem.

There is considerable freedom in the choice of how the lengths of the all-pairs shortest paths are computed. Perhaps the simplest formulation to write relies on a multicommodity flow for this task, leading to the following mixed-integer program.

## Model

$$
\begin{align*}
    \min \;& k \\
    \text{s.t.: (diameter) } & \forall s,t \in V, s\neq t:\quad p_{st} \le k \\
    \text{(all-pairs shortest paths) } & \forall s,t \in V, s\neq t:\quad p_{st} = \sum_{i \in V} \sum_{\substack{j \in V\\ j \neq i}} x_{stij} \\
    \text{(flow balance) } & \forall s,t \in V, s\neq t, \forall i \in V \setminus \{s,t\}:\quad \sum_{j \in V \setminus \{s,t,i\}} (x_{stij} - x_{stji}) = 0 
\end{align*}
$$
$$
\begin{align*}
    \text{(flow source) } & \forall s,t \in V, s\neq t:\quad \sum_{i \in V \setminus \{s,t\}} (x_{stsi} - x_{stis}) = 1 \\
    \text{(flow target) } & \forall s,t \in V, s\neq t:\quad \sum_{i \in V \setminus \{s,t\}} (x_{stit} - x_{stti}) = -1 \\
    \text{(}z,x \text{coupling) } & \forall s,t,i,j \in V, s\neq t, i\neq j:\quad x_{stij} \le z_{ij} \\
    \text{(degree) } & \forall i \in V:\quad \sum_{\substack{j \in V\\ j \neq i}} z_{ij} \le \text{max\_degree} \\
    &\forall i,j \in V, i\neq j:\quad z_{ij} \in \{0,1\} \\
    &\forall s,t \in V, s\neq t:\quad p_{st} \in \mathbb{Z}, p_{st} \ge 0 \\
    &\forall s,t,i,j \in V, s\neq t, i\neq j:\quad x_{stij} \in \{0,1\}
\end{align*} 
$$

## Description

This formulation minimizes the diameter of the network using a multicommodity flow approach to represent the all-pairs shortest paths. A different flow is used for each pair of nodes. 