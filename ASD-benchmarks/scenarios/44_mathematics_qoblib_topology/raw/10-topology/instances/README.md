# Instances for Topology Design

## Format Description

Each instance consists of a pair $(n, d)$ where $n$ is the number of nodes in the graph, and $d$ is the maximum degree.  
These two integers are specified on the first (non-comment) line of a file called `topology_n_d.dat`, and they are separated by a space.

## Instance Generation

The smaller instances ($n \leq 50$) were tested with Gurobi 11.0 using different integer programming models. 
The majority of these instances still have a remaining optimality gap after 2 hours, using default settings. 
Considering the size, their global solution may still be within reach of specialized algorithms.

The larger instances ($n > 50$) are taken from the [GraphGolf website](https://research.nii.ac.jp/graphgolf/2019/ranking.html)

For larger instances, integer programming models discussed in the existing literature fail to produce meaningful results. 
Feasible solutions are known for all the larger instances and are listed in the website given above. 
There is still a gap between known solutions and known dual bounds.

## Bounds Used

Three different integer models were tested for instances with $n \leq 50$. 
Two of those models (the "Seidel" models in the [models directory](./../models/)) require lower and upper bounds for the diameter. 
The bounds given to Gurobi are listed in the table below. 
If an instance is not listed in table, it was considered large and not tested with the integer programming formulation.

| Nodes | Degree | Diam LB | Diam UB |
| ----: | -----: | ------: | ------: |
|    15 |      3 |       3 |       3 |
|    15 |      4 |       2 |       2 |
|    20 |      3 |       3 |       4 |
|    20 |      4 |       3 |       3 |
|    20 |      5 |       2 |       2 |
|    25 |      3 |       4 |      10 |
|    25 |      4 |       3 |       7 |
|    25 |      5 |       2 |       6 |
|    25 |      6 |       2 |       2 |
|    30 |      4 |       3 |       8 |
|    30 |      5 |       3 |       7 |
|    30 |      6 |       2 |       5 |
|    35 |      5 |       3 |       8 |
|    35 |      6 |       2 |       5 |
|    40 |      6 |       3 |      13 |
|    50 |      4 |       3 |       8 |

These bounds are integrated in the [bounds](./bounds.csv) file - please don't delete it and change it only accordingly when adding tew instances as it is used in the generation of the LP files for [seidel_linear](./../models/seidel_linear/) and [seidel_quadratic](./../models/seidel_quadratic/).