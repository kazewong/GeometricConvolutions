from geometricconvolutions.geometric import (
    GeometricImage,
    get_unique_invariant_filters,
    LeviCivitaSymbol,
    make_all_operators,
    permutation_parity,
    TINY,
)
import pytest
import jax.numpy as jnp
import jax.random as random
import math

# Now test group actions on k-tensors:
def do_group_actions(operators):
    """
    # Notes:
    - This only does minimal tests!
    """
    D = len(operators[0])
    key = random.PRNGKey(0)

    for parity in [0, 1]:

        key, subkey = random.split(key)

        # vector dot vector
        v1 = GeometricImage(random.normal(subkey, shape=((1,)*D + (D,))), parity, D)
        key, subkey = random.split(key)
        v2 = GeometricImage(random.normal(subkey, shape=((1,)*D + (D,))), parity, D)
        dots = [(v1.times_group_element(gg)
                 * v2.times_group_element(gg)).contract(0, 1).data
                for gg in operators]
        dots = jnp.array(dots)
        if not jnp.allclose(dots, jnp.mean(dots)):
            print("failed (parity = {}) vector dot test.".format(parity))
            return False
        print("passed (parity = {}) vector dot test.".format(parity))

        # tensor times tensor
        key, subkey = random.split(key)
        T3 = GeometricImage(random.normal(subkey, shape=((1,)*D + (D, D))), parity, D)
        key, subkey = random.split(key)
        T4 = GeometricImage(random.normal(subkey, shape=((1,)*D + (D, D))), parity, D)
        dots = [(T3.times_group_element(gg)
                 * T4.times_group_element(gg)).contract(1, 2).contract(0, 1).data
                for gg in operators]
        dots = jnp.array(dots)
        if not jnp.allclose(dots, jnp.mean(dots)):
            print("failed (parity = {}) tensor times tensor test".format(parity))
            return False
        print("passed (parity = {}) tensor times tensor test".format(parity))

        # vectors dotted through tensor
        key, subkey = random.split(key)
        v5 = GeometricImage(random.normal(subkey, shape=((1,)*D + (D,))), 0, D)
        dots = [(v5.times_group_element(gg) * T3.times_group_element(gg)
                 * v2.times_group_element(gg)).contract(1, 2).contract(0, 1).data
                for gg in operators]
        dots = jnp.array(dots)
        if not jnp.allclose(dots, jnp.mean(dots)):
            print("failed (parity = {}) v T v test.".format(parity))
            return False
        print("passed (parity = {}) v T v test.".format(parity))

    return True

class TestMisc:

    def testPermutationParity(self):
        assert permutation_parity([0]) == 1
        assert permutation_parity((0,1)) == 1
        assert permutation_parity((1,0)) == -1
        assert permutation_parity([1,0]) == -1
        assert permutation_parity([1,1]) == 0
        assert permutation_parity([0,1,2]) == 1
        assert permutation_parity([0,2,1]) == -1
        assert permutation_parity([1,2,0]) == 1
        assert permutation_parity([1,0,2]) == -1
        assert permutation_parity([2,1,0]) == -1
        assert permutation_parity([2,0,1]) == 1
        assert permutation_parity([2,1,1]) == 0

    def testLeviCivitaSymbol(self):
        with pytest.raises(AssertionError):
            LeviCivitaSymbol.get(1)

        assert (LeviCivitaSymbol.get(2) == jnp.array([[0, 1], [-1, 0]], dtype=int)).all()
        assert (LeviCivitaSymbol.get(3) == jnp.array(
            [
                [[0,0,0], [0,0,1], [0,-1,0]],
                [[0,0,-1], [0,0,0], [1,0,0]],
                [[0,1,0], [-1,0,0], [0,0,0]],
            ],
            dtype=int)).all()

        assert LeviCivitaSymbol.get(2) is LeviCivitaSymbol.get(2) #test that we aren't remaking them

    def testGroupSize(self):
        for d in range(2,7):
            operators = make_all_operators(d)

            # test the group size
            assert len(operators) == 2*(2**(d-1))*math.factorial(d)

    def testGroup(self):
        for d in [2,3]: #could go longer, but it gets slow to test the closure
            operators = make_all_operators(d)
            D = len(operators[0])
            # Check that the list of group operators is closed, O(d^3)
            for gg in operators:
                for gg2 in operators:
                    product = (gg @ gg2).astype(int)
                    found = False
                    for gg3 in operators:
                        if jnp.allclose(gg3, product):
                            found = True
                            break

                    assert found

            # Check that gg.T is gg.inv for all gg in group
            for gg in operators:
                assert jnp.allclose(gg @ gg.T, jnp.eye(D))

            assert do_group_actions(operators)
