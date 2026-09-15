# 10 - Topology Design

**Alternative Names:** Graph Golf, Order/Degree Problem, Node-Degree-Diameter Problem

[← Back to Main Repository](../README.md)

---

## Overview

The Topology Design problem seeks to construct graphs with optimal communication properties given structural constraints. This problem has applications in network design, where minimizing communication latency (diameter) while limiting connection costs (degree) is crucial.

**External Resources:**
- http://research.nii.ac.jp/graphgolf/
- https://research.nii.ac.jp/graphgolf/problem.html

## Problem Description

Given:
- A target number of nodes $n$
- A maximum degree constraint $\Delta$

**Objective:** Find a graph $G = (V,E)$ with $|V| = n$ and maximum degree $\Delta(G) \leq \Delta$ that minimizes the diameter.

**Diameter:** The diameter of a graph is the maximum shortest path distance between any pair of vertices:
$$
\text{diam}(G) = \max_{u,v \in V} d(u,v)
$$

**Note:** We do not use average shortest path length as a tiebreaker.

## Directory Contents

- **[instances/](instances/)** - Topology design problem instances
- **[models/](models/)** - Mathematical model formulations
- **[solutions/](solutions/)** - Optimal or best-known solutions
- **[check/](check/)** - Solution verification tools
- **[info/](info/)** - Additional documentation and papers
- **[misc/](misc/)** - Utility scripts and generators
- **[submissions/](submissions/)** - Community solution submissions

## References

* **Kitasuka, T., Matsuzaki, T., Iida, M.** (2018). [Order adjustment approach using Cayley graphs for the order/degree problem](https://www.jstage.jst.go.jp/article/transinf/E101.D/12/E101.D_2018PAP0008/_pdf). IEICE TRANSACTIONS on Information and Systems, 101(12), 2908-2915.

* **Waniek, R.** Master's thesis, TU Berlin. Contains extensive references, mathematical models, and useful code (in German).

Both references are available in the [info/](info/) directory.
