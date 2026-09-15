# Models for Topology Design

We provide three mathematical programming formulations for the problem.
The three models differ in terms of how they model the length of the shortest path between each source-destination pair.

- The [first model](./flow_mip/) uses a standard $s$-$t$ flow model to compute shortest path values. 
- The [second model](./seidl_quadratic/) uses Seidel's quadratic all-pairs shortest path formulation. 
- The [third model](./seidl_linear/) is a linearization of Seidel's quadratic model. 

See each model file for additional information. 
In particular, some models may take additional parameters as input, such as lower and upper bounds to tighten some variables (which may have significant impact on the practical performance). 
These parameters are instance-dependent and the model files assign extremely loose default values.
