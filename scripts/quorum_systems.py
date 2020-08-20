import matplotlib
matplotlib.use('pdf')
font = {'size': 14}
matplotlib.rc('font', **font)

from typing import Any, Dict, Iterator, List, NamedTuple, Set, Tuple
import itertools
import math
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pulp


# TODO(mwhittaker): Implement some other metrics of fault tolerance and of
# simplicity. Right now, there's a lot of optimal quorum systems. We'd like to
# select the ones that are most live. If there's a tie on that too, then we can
# prefer ones that aren't nested as deep for example.

# TODO(mwhittaker): Think about how to compute load when we average over a
# number of different quorum systems.

class Workload:
    def __init__(self, fr: float = None, fw: float = None) -> None:
        if fr is not None:
            self.fr = fr
        else:
            assert fw is not None
            self.fr = 1 - fw

        if fw is not None:
            self.fw = fw
        else:
            assert fr is not None
            self.fw = 1 - fr

        assert self.fr + self.fw == 1


class QuorumSystem:
    def read_quorums(self) -> Iterator[Set[str]]:
        raise NotImplementedError()

    def write_quorums(self) -> Iterator[Set[str]]:
        raise NotImplementedError()

    def load(self, workload: Workload, balanced: bool = False) -> float:
        raise NotImplementedError()

    def read_resilience(self) -> int:
        return self.min_read_failure() - 1

    def write_resilience(self) -> int:
        return self.min_write_failure() - 1

    def resilience(self) -> int:
        return min(self.min_read_failure(), self.min_write_failure()) - 1

    def min_read_failure(self) -> int:
        raise NotImplementedError()

    def min_write_failure(self) -> int:
        raise NotImplementedError()

    def to_graph(self) -> nx.Graph:
        def canonicalize(nodes: Set[str]) -> str:
            return ','.join(sorted(list(nodes)))

        g = nx.Graph()

        for rq in self.read_quorums():
            for x in rq:
                g.add_edge(f'r({canonicalize(rq)})', x)

        for wq in self.write_quorums():
            for x in wq:
                g.add_edge(f'w({canonicalize(wq)})', x)

        return g


class Node(QuorumSystem):
    def __init__(self, name: str) -> None:
        self._name = name

    def __repr__(self) -> str:
        return f'Node({self._name})'

    def __str__(self) -> str:
        return self._name

    def read_quorums(self) -> Iterator[Set[str]]:
        yield {self._name}

    def write_quorums(self) -> Iterator[Set[str]]:
        yield {self._name}

    def load(self, workload: Workload, balanced: bool = False) -> float:
        return 1

    def min_read_failure(self) -> int:
        return 1

    def min_write_failure(self) -> int:
        return 1


class Simple(QuorumSystem):
    def __init__(self, r: int, xs: List[QuorumSystem]) -> None:
        self._xs = xs
        self._n = len(xs)
        self._r = r
        self._w = self._n - self._r + 1
        assert(1 <= self._r <= self._n)

    def __str__(self) -> str:
        xs_str = '[' + ', '.join(str(x) for x in self._xs) + ']'
        return f'S(r={self._r}, {xs_str})'

    def read_quorums(self) -> Iterator[Set[str]]:
        for systems in itertools.combinations(self._xs, self._r):
            for qs in itertools.product(*[s.read_quorums() for s in systems]):
                yield {n for q in qs for n in q}

    def write_quorums(self) -> Iterator[Set[str]]:
        for systems in itertools.combinations(self._xs, self._w):
            for qs in itertools.product(*[s.write_quorums() for s in systems]):
                yield {n for q in qs for n in q}

    def load(self, workload: Workload, balanced: bool = False) -> float:
        def canonicalize(nodes: Set[str]) -> str:
            return ','.join(sorted(list(nodes)))

        # For every node, record which read quorums it belongs to.
        read_quorums: Dict[str, List[pulp.LpVariable]] = dict()
        read_weights: List[pulp.LpVariable] = []
        for rq in self.read_quorums():
            v = pulp.LpVariable(f'r({canonicalize(rq)})', 0, 1)
            read_weights.append(v)

            for n in rq:
                if n not in read_quorums:
                    read_quorums[n] = []
                read_quorums[n] += [v]

        # For every node, record which write quorums it belongs to.
        write_quorums: Dict[str, List[pulp.LpVariable]] = dict()
        write_weights: List[pulp.LpVariable] = []
        for wq in self.write_quorums():
            v = pulp.LpVariable(f'w({canonicalize(wq)})', 0, 1)
            write_weights.append(v)

            for n in wq:
                if n not in write_quorums:
                    write_quorums[n] = []
                write_quorums[n] += [v]

        # Form the linear program to find the load.
        problem = pulp.LpProblem("load", pulp.LpMinimize)

        # If we're trying to balance the strategy, then we want to minimize the
        # pairwise absolute differences between the read probabilities and the
        # write probabilities.
        l = pulp.LpVariable('l', 0, 1)
        if not balanced:
            problem += l
        else:
            scale = 1000 * len(read_weights) ** 2 + len(write_weights) ** 2
            objective = scale * l

            for (rw, weights) in [('r', read_weights), ('w', write_weights)]:
                for i in range(len(weights)):
                    for j in range(i + 1, len(weights)):
                        vi = weights[i]
                        vj = weights[j]
                        v = pulp.LpVariable(f'{vi.name},{vj.name}', 0, 1)
                        problem += (vi - vj <= v, f'{vi.name}, {vj.name} upper')
                        problem += (-v <= vi - vj, f'{vi.name}, {vj.name} lower')
                        objective += v
            problem += objective

        problem += (sum(read_weights) == 1, 'valid read strategy')
        problem += (sum(write_weights) == 1, 'valid write strategy')
        for node in read_quorums.keys() | write_quorums.keys():
            node_load: pulp.LpAffineExpression = 0
            if node in read_quorums:
                node_load += workload.fr * sum(read_quorums[node])
            if node in write_quorums:
                node_load += workload.fw * sum(write_quorums[node])
            problem += (node_load <= l, node)

        # print(problem)
        problem.solve(pulp.apis.PULP_CBC_CMD(msg=False))
        # for v in read_weights + write_weights:
        #     print(f'{v.name} = {v.varValue}')
        return l.varValue

    def min_read_failure(self) -> int:
        return sum(sorted([x.min_read_failure() for x in self._xs])[:self._w])

    def min_write_failure(self) -> int:
        return sum(sorted([x.min_write_failure() for x in self._xs])[:self._r])


class Paths1(QuorumSystem):
    """
       o     o
       |     |
    o--a--o--b--o
       |  |  |
       o--c--o
       |  |  |
    o--d--o--e--o
       |     |
       o     o
    """
    def __repr__(self) -> str:
        return f'Paths(1)'

    def __str__(self) -> str:
        return f'Paths(1)'

    def read_quorums(self) -> Iterator[Set[str]]:
        yield {'a', 'b'}
        yield {'a', 'c', 'e'}
        yield {'d', 'e'}
        yield {'d', 'c', 'b'}

    def write_quorums(self) -> Iterator[Set[str]]:
        yield {'a', 'd'}
        yield {'a', 'c', 'e'}
        yield {'b', 'e'}
        yield {'b', 'c', 'd'}

    def load(self, workload: Workload, balanced: bool = False) -> float:
        raise NotImplementedError()

    def min_read_failure(self) -> int:
        return 2

    def min_write_failure(self) -> int:
        return 2


def partition(xs: List[Any]) -> Iterator[List[List[Any]]]:
    if xs == []:
        return

    for p in _partition_helper(xs, len(xs)):
        yield p


def _partition_helper(xs: List[Any], max_size: int) -> Iterator[List[List[Any]]]:
    if xs == []:
        yield []
        return

    for left_size in range(min(len(xs), max_size), 0, -1):
        for p in _partition_helper(xs[left_size:], max_size = left_size):
            yield [xs[:left_size]] + p

def systems(xs: List['str']) -> Iterator[QuorumSystem]:
    for x in _systems_helper([Node(x) for x in xs]):
        yield x

def _systems_helper(xs: List[Node]) -> Iterator[QuorumSystem]:
    if len(xs) == 0:
        return

    if len(xs) == 1:
        yield xs[0]
        return

    for p in partition(xs):
        if len(p) == 1:
            pass
        else:
            for ys in itertools.product(*[_systems_helper(x) for x in p]):
                for r in range(1, len(p) + 1):
                    yield Simple(r, list(ys))


def min_load(f: int, workload: Workload, n: int) -> float:
    return min(
        p.load(workload)
        for p in systems([str(i) for i in range(n)])
        if p.resilience() >= f
    )


def sharded_load(f: int, workload: Workload, n: int) -> float:
    fr = workload.fr
    fw = workload.fw
    return ((f + 1) / n) * (fr**2 + (n-1)*fr*fw + fw**2)

#
#
# class QuorumSystem(NamedTuple):
#     R: int
#     C: int
#     r: int
#     nr: int
#     c: int
#     nc: int
#
#     def is_valid(self) -> bool:
#         return all([self.R >= 1, self.C >= 1, self.r <= self.R,
#                     self.nr <= self.C, self.c <= self.C, self.nc <= self.R])
#
#
#     def is_safe(self, w: Workload) -> bool:
#         sr = self.C - self.nr
#         sc = self.R - self.nc
#         return all([self.nr + self.c > self.C,
#                     self.r + self.nc > self.R,
#                     self.R >= math.floor(w.f / (sr + 1)) + self.r,
#                     self.C >= math.floor(w.f / (sc + 1)) + self.c])
#
#
#     def to_ascii(self) -> str:
#         grid = [[' . ' for _ in range(self.C)] for _ in range(self.R)]
#
#         for row in range(self.r):
#             for col in range(self.nr):
#                 grid[row][col] = ' r '
#
#         for row in range(self.R - 1, self.R - 1 - self.nc, -1):
#             for col in range(self.C - 1, self.C - 1 - self.c, -1):
#                 if grid[row][col] == ' r ':
#                     grid[row][col] = ' x '
#                 else:
#                     grid[row][col] = ' w '
#
#         bar = '+' + ('---' * self.C) + '+'
#         return '\n'.join([bar] + ['|' + ''.join(r) + '|' for r in grid] + [bar])
#
#
# def load(workload: Workload, qs: QuorumSystem) -> float:
#     assert(workload.is_valid())
#     assert(qs.is_valid())
#     assert(qs.is_safe(workload))
#     return ((workload.fr * (qs.r / qs.R) * (qs.nr / qs.C)) +
#             (workload.fw * (qs.c / qs.C) * (qs.nc / qs.R)))
#
#
# def ranked(workload: Workload, n: int) -> List[Tuple[QuorumSystem, float]]:
#     assert(workload.is_valid())
#
#     loads = [
#         (qs, load(workload, qs))
#         for R in range(1, n + 1)
#         for C in range(1, math.floor(n / R) + 1)
#         for r in range(1, R + 1)
#         for c in range(1, C + 1)
#         for nr in range(1, C + 1)
#         for nc in range(1, R + 1)
#         for qs in [QuorumSystem(R, C, r, nr, c, nc)]
#         if qs.is_valid() and qs.is_safe(workload)
#     ]
#
#     loads.sort(key=lambda x: x[1])
#     return loads
#
#
# def optimal(workload: Workload, n: int) -> List[QuorumSystem]:
#     assert(workload.is_valid())
#
#     quorum_systems = [
#         qs
#         for R in range(1, n + 1)
#         for C in range(1, math.floor(n / R) + 1)
#         for r in range(1, R + 1)
#         for c in range(1, C + 1)
#         for nr in range(1, C + 1)
#         for nc in range(1, R + 1)
#         for qs in [QuorumSystem(R, C, r, nr, c, nc)]
#         if qs.is_valid() and qs.is_safe(workload)
#     ]
#
#     o = min([load(workload, qs) for qs in quorum_systems])
#     return [qs for qs in quorum_systems if load(workload, qs) == o]


def plot_load():
    fig, ax = plt.subplots(1, 1, figsize=(6.4, 4.8))

    # Plot sharded load.
    ns = [3, 4, 5, 6, 7]
    colors = []
    for n in ns:
        fw = np.arange(0, 1, 1/1000)
        fr = 1 - fw
        l = [sharded_load(f=1, workload=Workload(fr=x), n=n) for x in fr]
        colors.append(ax.plot(fw, l, label=f'sharded n={n}')[0].get_color())

    # Plot load.
    for (n, color) in zip(ns, colors):
        fw = np.array([0, 0.1, 0.2, 0.3, 0.4, 0.5])
        fr = 1 - fw
        l = [min_load(f=1, workload=Workload(fr=x), n=n) for x in fr]
        fw = np.concatenate([fw, fw + 0.5])
        l = (np.concatenate([l, np.flip(l)]))
        ax.plot(fw, l, 'o--', color=color, label=f'n={n}')

    ax.set_title('f = 1')
    ax.set_xlabel('Write fraction')
    ax.set_ylabel('Load')
    ax.grid()
    ax.legend(loc='center left', bbox_to_anchor=(1, 0.5))
    output_filename = 'load.pdf'
    fig.savefig(output_filename, bbox_inches='tight')
    print(f'Wrote plot to {output_filename}.')


def find_isomorphism():
    paths1 = Paths1().to_graph()
    for system in systems(['a', 'b', 'c', 'd', 'e']):
        g = system.to_graph()
        matcher = nx.isomorphism.GraphMatcher(g, paths1)
        if matcher.subgraph_is_isomorphic():
            print(system)
            return


def main():
    # print_load()
    find_isomorphism()
    pass

if __name__ == '__main__':
    main()
