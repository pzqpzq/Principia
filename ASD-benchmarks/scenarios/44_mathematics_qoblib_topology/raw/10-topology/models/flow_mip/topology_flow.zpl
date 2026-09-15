# This file is part of QOBLIB - Quantum Optimization Benchmarking Library
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
#     http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

param filename := "topology_40_5.dat";

param nodes := read filename as "1n" use 1 comment "#";
param degree := read filename as "2n" use 1 comment "#";

set N := { 0..nodes-1 };
set E := { <i,j> in N * N with i != j };
set F := { <i,j> in N * N with i < j };

# Diameter of the graph
var diameter integer <= nodes - 1;
# Length of the shortest path between a pair of nodes
var SP[F] integer <= nodes - 1;
# Is there an arc between two nodes
var z[F] binary;
# Flow variables
var x[F * E] binary;

minimize DIAM: diameter;

subto diameter: forall <s,t> in F : SP[s,t] <= diameter;
subto APSP: forall <s,t> in F : SP [s, t] == sum <s,t,i,j> in F * E : x[s,t,i,j ];
subto SPtransit : forall <s,t> in F : forall <i> in N \ {s,t}: sum <s,t,i,j> in F * E : x[s,t,i,j] - sum <s,t,j,i> in F * E : x[s,t,j,i] == 0;
subto SPsource : forall <s,t> in F : sum <s,t,s,j> in F * E : x[s,t,s,j] - sum <s,t,j,s> in F * E : x[s,t,j,s] == 1;
subto SPtarget : forall <s,t> in F : sum <s,t,t,j> in F * E : x[s,t,t,j] - sum <s,t,j,t> in F * E : x[s,t,j,t] == -1;
subto degree : forall <i > in N : sum <i,j> in F : z[i,j] + sum <j,i> in F : z[j,i] <= degree;
subto ZXlink : forall <s,t,i,j> in F * F : z[i,j] >= x [s,t,i,j] and z[i,j] >= x[s,t,j,i];
